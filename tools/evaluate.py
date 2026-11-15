"""Test invoices: invoices with answers a person confirmed, used to measure how well checks work.

Usage:
  ./.tools/uv run tools/evaluate.py add <invoice> [--aside]   # from a reviewed result; usually done on the page
  ./.tools/uv run tools/evaluate.py clear-latest               # before checking all test invoices again
  ./.tools/uv run tools/evaluate.py score                      # compare the latest checks with the confirmed answers
"""

from __future__ import annotations

import argparse
import shutil
import sys
from copy import deepcopy

from checks import evaluate as evaluate_rules, final_fields
from common import (
    WorkspaceError, current_project, invoice_path, load_config, load_json, log, now_iso, print_json,
    project_dir, result_path, save_json, set_dirs,
)
from values import same_value


def truth_dir(slug: str):
    return project_dir(slug) / "evaluation" / "truth"


def ai_only(result: dict) -> dict:
    """The result as the assistant produced it, before any reviewer correction."""
    original = deepcopy(result.get("ai_original") or result)
    for key in ("review", "ai_original", "rule_results", "status", "rules_checked_at"):
        original.pop(key, None)
    return original


def add(slug: str, invoice_id: str, aside: bool, who: str = "staff") -> dict:
    result = load_json(result_path(slug, invoice_id))
    if not result:
        raise WorkspaceError(f"'{invoice_id}' has not been checked yet.")
    if (result.get("review") or {}).get("status") != "confirmed":
        raise WorkspaceError("Confirm the review of this invoice first, so only checked answers become test answers.")
    config = load_config(slug)
    fields = final_fields(result)
    type_id = result.get("type_id")
    names = [f["name"] for f in config["fields"] if f["type_id"] == type_id]
    truth = {
        "invoice": invoice_id,
        "type_id": type_id,
        "fields": {name: (fields.get(name) or {}).get("value") if (fields.get(name) or {}).get("status") != "not_found" else None
                   for name in names},
        "rules": {o["rule_id"]: o["outcome"] for o in result.get("rule_results", []) if o["outcome"] in ("passed", "failed")},
        "aside": aside,
        "confirmed_by": (result.get("review") or {}).get("by", "staff"),
        "confirmed_at": now_iso(),
    }
    source = invoice_path(slug, invoice_id)
    invoices_dir, latest_dir = set_dirs(slug, "evaluation")
    invoices_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(source, invoices_dir / source.name)
    save_json(truth_dir(slug) / f"{invoice_id}.json", truth)
    latest = ai_only(result)
    latest.update(evaluate_rules(latest, config, {}))
    save_json(latest_dir / f"{invoice_id}.json", latest)
    log(slug, who, "test invoice added", {"invoice": invoice_id, "kept aside": aside})
    return truth


def clear_latest(slug: str) -> int:
    _, latest_dir = set_dirs(slug, "evaluation")
    removed = 0
    for path in latest_dir.glob("*.json") if latest_dir.exists() else []:
        path.unlink()
        removed += 1
    log(slug, "assistant", "test invoices cleared for a new run", {"cleared": removed})
    return removed


def _empty_counts() -> dict:
    return {"matched": 0, "missed": 0, "false_alarm": 0, "unclear": 0}


def score(slug: str, who: str = "assistant") -> dict:
    config = load_config(slug)
    kinds = {(f["type_id"], f["name"]): f.get("kind", "text") for f in config["fields"]}
    names = {r["id"]: r.get("name", r["id"]) for r in config["rules"]}
    _, latest_dir = set_dirs(slug, "evaluation")
    groups = {"main": {"invoices": 0, "type_correct": 0, "fields_right": 0, "fields_total": 0, "rules": {}},
              "aside": {"invoices": 0, "type_correct": 0, "fields_right": 0, "fields_total": 0, "rules": {}}}
    details, missing = [], []
    for truth_path in sorted(truth_dir(slug).glob("*.json")):
        truth = load_json(truth_path)
        latest = load_json(latest_dir / truth_path.name)
        if not latest:
            missing.append(truth["invoice"])
            continue
        group = groups["aside" if truth.get("aside") else "main"]
        group["invoices"] += 1
        group["type_correct"] += int(latest.get("type_id") == truth["type_id"])
        fields = final_fields(latest)
        wrong_fields = []
        for name, expected in truth["fields"].items():
            got = (fields.get(name) or {}).get("value") if (fields.get(name) or {}).get("status") != "not_found" else None
            group["fields_total"] += 1
            if same_value(expected, got, kinds.get((truth["type_id"], name), "text")):
                group["fields_right"] += 1
            else:
                wrong_fields.append({"field": name, "expected": expected, "got": got})
        outcomes = {o["rule_id"]: o["outcome"] for o in latest.get("rule_results", [])}
        rule_notes = []
        for rule_id, expected in truth["rules"].items():
            got = outcomes.get(rule_id, "not checked")
            counts = group["rules"].setdefault(rule_id, _empty_counts())
            if got == "unclear" or got == "not checked":
                counts["unclear"] += 1
                kind = "unclear"
            elif expected == "failed" and got != "failed":
                counts["missed"] += 1
                kind = "missed"
            elif expected == "passed" and got == "failed":
                counts["false_alarm"] += 1
                kind = "false_alarm"
            else:
                counts["matched"] += 1
                kind = "matched"
            if kind != "matched":
                rule_notes.append({"rule": rule_id, "name": names.get(rule_id, rule_id), "expected": expected, "got": got, "kind": kind})
        details.append({"invoice": truth["invoice"], "aside": truth.get("aside", False),
                        "type_correct": latest.get("type_id") == truth["type_id"],
                        "wrong_fields": wrong_fields, "rule_notes": rule_notes})
    for group in groups.values():
        group["rules"] = [{"rule_id": r, "name": names.get(r, r), **c} for r, c in sorted(group["rules"].items())]
        totals = _empty_counts()
        for row in group["rules"]:
            for key in totals:
                totals[key] += row[key]
        group["totals"] = totals
    run = {"at": now_iso(), "groups": groups, "invoices": details, "not_checked_yet": missing}
    stamp = run["at"].replace(":", "").replace("+0000", "Z")
    save_json(project_dir(slug) / "evaluation" / "runs" / f"{stamp}.json", run)
    main_totals = groups["main"]["totals"]
    log(slug, who, "test invoices scored", {"missed": main_totals["missed"], "false alarms": main_totals["false_alarm"],
                                            "matched": main_totals["matched"], "invoices": groups["main"]["invoices"]})
    return run


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["add", "clear-latest", "score"])
    parser.add_argument("invoice", nargs="?")
    parser.add_argument("--aside", action="store_true")
    args = parser.parse_args()
    try:
        slug = current_project()
        if args.command == "add":
            if not args.invoice:
                raise WorkspaceError("Say which invoice to add.")
            print_json(add(slug, args.invoice, args.aside, who="assistant"))
        elif args.command == "clear-latest":
            print_json({"cleared": clear_latest(slug)})
        else:
            print_json(score(slug))
    except WorkspaceError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
