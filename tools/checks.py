"""Check a result against the project's confirmed rules, the same way every time.

The assistant writes what it read into results/<invoice>.json. This tool validates that file,
applies the rules, adds checks across all invoices of the project (duplicate invoice numbers)
and writes the outcome back. Reviewer corrections in the "review" part always win.

Usage:
  ./.tools/uv run tools/checks.py run <invoice>
  ./.tools/uv run tools/checks.py run --all
"""

from __future__ import annotations

import argparse
import re
import sys

from common import WorkspaceError, current_project, load_config, load_json, now_iso, print_json, project_dir
from values import parse_amount, parse_date, plain

FIELD_STATUSES = {"found", "uncertain", "not_found"}
VERDICTS = {"pass", "fail", "unclear"}
RULE_OUTCOMES = ("passed", "failed", "unclear", "not_applicable")
DUPLICATE_RULE = "DUPLICATE_NUMBER"


def validate(result: dict, config: dict) -> list[str]:
    problems = []
    type_ids = {t["id"] for t in config["invoice_types"]}
    if result.get("type_id") not in type_ids:
        problems.append(f"type_id must be one of {sorted(type_ids)}.")
    known = {f["name"] for f in config["fields"] if f["type_id"] == result.get("type_id")}
    if not isinstance(result.get("fields", {}), dict) or not isinstance(result.get("visual", {}), dict):
        return ["Fields and visual verdicts must be objects."]
    for name, field in result.get("fields", {}).items():
        if name not in known:
            problems.append(f"Field '{name}' is not defined for type {result.get('type_id')}.")
        if not isinstance(field, dict) or field.get("status") not in FIELD_STATUSES:
            problems.append(f"Field '{name}' needs a status of found, uncertain or not_found.")
            continue
        problems.extend(_box_problems(f"Field '{name}'", field))
    for rule_id, verdict in (result.get("visual") or {}).items():
        if not isinstance(verdict, dict) or verdict.get("verdict") not in VERDICTS:
            problems.append(f"Visual rule '{rule_id}' needs a verdict of pass, fail or unclear.")
            continue
        problems.extend(_box_problems(f"Visual rule '{rule_id}'", verdict))
    return problems


def _box_problems(label: str, item: dict) -> list[str]:
    box = item.get("box")
    if box is None:
        return []
    if (not isinstance(box, list) or len(box) != 4 or not all(isinstance(v, (int, float)) for v in box)
            or not (0 <= box[0] < box[2] <= 1 and 0 <= box[1] < box[3] <= 1)):
        return [f"{label} has an invalid box; use the numbers printed by grid.py finalize."]
    if type(item.get("page")) is not int or item["page"] < 1:
        return [f"{label} has a box but no page number."]
    return []


def final_fields(result: dict) -> dict[str, dict]:
    """The AI's fields with reviewer corrections applied."""
    fields = {name: dict(value) for name, value in (result.get("fields") or {}).items()}
    for name, value in ((result.get("review") or {}).get("fields") or {}).items():
        entry = fields.setdefault(name, {"page": None, "box": None})
        entry["value"] = value
        entry["status"] = "found" if value not in (None, "") else "not_found"
        entry["corrected"] = True
    for name, location in (((result.get("review") or {}).get("evidence") or {}).get("fields") or {}).items():
        if name in fields:
            fields[name].update(location)
    return fields


def _field_value(fields: dict, name: str):
    field = fields.get(name) or {}
    if field.get("status") == "not_found":
        return None
    value = field.get("value")
    return None if value in (None, "") else value


def apply_rule(rule: dict, result: dict, fields: dict, project: dict) -> dict:
    check, name = rule.get("check"), rule.get("field")
    outcome, message, evidence = "passed", "", None
    if check == "visual":
        verdict = (result.get("visual") or {}).get(rule["id"])
        if not verdict:
            outcome, message = "unclear", "Not judged in this check."
        else:
            outcome = {"pass": "passed", "fail": "failed", "unclear": "unclear"}[verdict["verdict"]]
            message = verdict.get("reason", "")
            if verdict.get("box"):
                evidence = {"page": verdict.get("page"), "box": verdict["box"]}
    else:
        value = _field_value(fields, name)
        field = fields.get(name) or {}
        if field.get("box"):
            evidence = {"page": field.get("page"), "box": field["box"]}
        if check == "required":
            if value is None:
                outcome, message = "failed", f"{name} was not found."
            elif field.get("status") == "uncertain":
                outcome, message = "unclear", f"{name} was read but is uncertain."
        elif value is None:
            outcome, message = "not_applicable", f"{name} is empty, so this rule does not apply."
        elif check == "regex":
            if not re.fullmatch(str(rule.get("value", "")), str(value).strip()):
                outcome, message = "failed", f"{name} '{value}' does not have the expected format."
        elif check == "range":
            number = parse_amount(value)
            low, high = (parse_amount(part) for part in str(rule.get("value", ",")).split(",")[:2])
            if number is None:
                outcome, message = "unclear", f"{name} '{value}' is not a number."
            elif (low is not None and number < low) or (high is not None and number > high):
                outcome, message = "failed", f"{name} {number:g} is outside {rule.get('value')}."
        elif check == "enum":
            allowed = [plain(v) for v in str(rule.get("value", "")).split(",") if v.strip()]
            if plain(value) not in allowed:
                outcome, message = "failed", f"{name} '{value}' is not one of: {rule.get('value')}."
        elif check == "date_in_period":
            day = parse_date(value)
            start, end = parse_date(project.get("period_start")), parse_date(project.get("period_end"))
            if day is None:
                outcome, message = "unclear", f"{name} '{value}' could not be read as a date."
            elif not (start and end):
                outcome, message = "unclear", "The project period is not set."
            elif not start <= day <= end:
                outcome, message = "failed", f"{day.isoformat()} is outside the project period {start} to {end}."
        else:
            outcome, message = "unclear", f"Unknown check type '{check}'."
    if outcome == "failed" and not message:
        message = rule.get("description", "")
    return {"rule_id": rule["id"], "name": rule.get("name", rule["id"]), "severity": rule.get("severity", "error"),
            "outcome": outcome, "message": message, "evidence": evidence}


def reviewed_findings(result: dict, findings: list[dict]) -> list[dict]:
    """Keep the initial reading, the automatic check and the reviewer's explanation distinct."""
    review = result.get("review") or {}
    if not review:
        return findings
    originals = {item["rule_id"]: item for item in (result.get("ai_original") or {}).get("rule_results", [])}
    decisions = review.get("rules") or {}
    reasons = review.get("rule_reasons") or {}
    reviewed = []
    for finding in findings:
        key = finding["rule_id"]
        # Older reviewed records stored the pre-override outcome in ai_outcome
        # and left the automatic explanation in message.
        automatic = finding.get("check_outcome", finding.get("ai_outcome", finding["outcome"]))
        explanation = finding.get("check_message", finding.get("message", ""))
        original = originals.get(key, {})
        decision = decisions.get(key)
        outcome = decision if decision in RULE_OUTCOMES else automatic
        reason = reasons.get(key, "")
        location = (review.get("evidence") or {}).get("rules", {}).get(key)
        reviewed.append(finding | {
            "evidence": location or finding.get("evidence"),
            "ai_outcome": original.get("ai_outcome", original.get("outcome", automatic)),
            "ai_message": original.get("ai_message", original.get("message", explanation)),
            "check_outcome": automatic, "check_message": explanation,
            "outcome": outcome, "overridden": decision in RULE_OUTCOMES,
            "review_reason": reason, "message": reason or (explanation if outcome == automatic else ""),
        })
    return reviewed


def evaluate(result: dict, config: dict, duplicates: dict[str, list[str]]) -> dict:
    fields = final_fields(result)
    project = config["project"]
    rules = [r for r in config["rules"]
             if r.get("status") == "confirmed" and r.get("enabled", True)
             and r.get("type_id") in (result.get("type_id"), "ALL")]
    outcomes = [apply_rule(rule, result, fields, project) for rule in rules]
    number = _field_value(fields, "invoice_number")
    others = duplicates.get(plain(number), []) if number else []
    others = [i for i in others if i != result.get("invoice")]
    if others:
        outcomes.append({"rule_id": DUPLICATE_RULE, "name": "Invoice number used only once", "severity": "warning",
                         "outcome": "failed", "message": f"Number {number} also appears on: {', '.join(others)}.",
                         "evidence": None})
    outcomes = reviewed_findings(result, outcomes)
    failed_errors = [o for o in outcomes if o["outcome"] == "failed" and o["severity"] == "error"]
    needs_look = [o for o in outcomes if o["outcome"] == "unclear" or (o["outcome"] == "failed" and o["severity"] != "error")]
    uncertain = [n for n, f in fields.items() if f.get("status") == "uncertain"]
    if not rules:
        status = "no applicable rules"
    elif failed_errors:
        status = "fails rules"
    elif needs_look or uncertain or result.get("questions"):
        status = "needs a look"
    else:
        status = "passes"
    return {"rule_results": outcomes, "rules_checked": len(rules), "status": status, "rules_checked_at": now_iso()}


def record_for_display(stored: dict | None) -> dict | None:
    """Read older results without rewriting the files or rerunning current rules."""
    if stored is None:
        return None
    result = {k: v for k, v in stored.items() if k != "pending_recheck"}
    if "rule_results" in result:
        result["rule_results"] = reviewed_findings(result, result["rule_results"])
        result["rules_checked"] = sum(o["rule_id"] != DUPLICATE_RULE for o in result["rule_results"])
        if not result["rules_checked"]:
            result["status"] = "no applicable rules"
    return result


def checked_result(slug: str, result: dict) -> dict:
    config = load_config(slug)
    problems = validate(result, config)
    if problems:
        raise WorkspaceError("The result file needs fixing:\n- " + "\n- ".join(problems))
    # Evaluate the incoming reading in memory. It must not temporarily replace
    # a confirmed result just to participate in the duplicate-number check.
    results_dir = project_dir(slug) / "results"
    duplicates: dict[str, list[str]] = {}
    for path in results_dir.glob("*.json"):
        if path.name.startswith(".") or path.stem == result["invoice"]:
            continue
        other = load_json(path)
        number = _field_value(final_fields(other), "invoice_number")
        if number:
            duplicates.setdefault(plain(number), []).append(path.stem)
    return result | evaluate(result, config, duplicates)


def run(slug: str, invoice_id: str) -> dict:
    from results import recalculate
    return recalculate(slug, invoice_id)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["run"])
    parser.add_argument("invoice", nargs="?")
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()
    try:
        slug = current_project()
        if args.all:
            results_dir = project_dir(slug) / "results"
            ids = sorted(p.stem for p in results_dir.glob("*.json") if not p.name.startswith(".")) if results_dir.exists() else []
        elif args.invoice:
            ids = [args.invoice]
        else:
            raise WorkspaceError("Say which invoice, or use --all.")
        summary = []
        for invoice_id in ids:
            result = run(slug, invoice_id)
            summary.append({
                "invoice": invoice_id, "status": result["status"],
                "failed": [o["rule_id"] for o in result["rule_results"] if o["outcome"] == "failed"],
                "unclear": [o["rule_id"] for o in result["rule_results"] if o["outcome"] == "unclear"],
            })
        print_json(summary)
    except WorkspaceError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
