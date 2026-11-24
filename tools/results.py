"""Save what the assistant read from an invoice, then run the rules and draw the marks.

Usage:
  ./.tools/uv run tools/results.py save <invoice> <draft.json>

The draft is a JSON object:
{
  "type_id": "VOLUNTARIOS",
  "type_reason": "Signed receipt for a monthly volunteer bonus",
  "fields": {
    "total_amount": {"value": "30.000", "status": "found", "page": 1, "box": [0.71, 0.43, 0.88, 0.47]},
    "invoice_number": {"value": null, "status": "not_found"}
  },
  "visual": {
    "R_VOL_101": {"verdict": "pass", "reason": "Funding stamp with file number and caption", "page": 1, "box": [...]}
  },
  "questions": ["Is the proof of payment in a separate file?"],
  "summary": "One or two plain sentences for the reviewer."
}
status is found, uncertain or not_found. verdict is pass, fail or unclear. Boxes come from
grid.py finalize; leave "box" out when a value could not be confirmed on the page.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

from checks import DUPLICATE_RULE, RULE_OUTCOMES, checked_result, record_for_display
from common import (
    WorkspaceError, current_project, invoice_display_name, invoice_path, load_config, load_json, log, now_iso, print_json,
    project_dir, rel, result_path, save_json,
)
from marks import draw
from report import summary_row
from review_lock import review_lock

ALLOWED_KEYS = {"type_id", "type_reason", "fields", "visual", "questions", "summary"}


def revision(result: dict | None) -> str | None:
    if not result:
        return None
    if "revision" in result:
        return result["revision"]
    # Legacy rows have no ID. Hash the same canonical representation on read
    # and save, so a stale browser can never approve a different legacy row.
    payload = json.dumps(record_for_display(result), sort_keys=True, ensure_ascii=False).encode()
    return hashlib.sha256(payload).hexdigest()


def is_confirmed(result: dict | None) -> bool:
    return ((result or {}).get("review") or {}).get("status") == "confirmed"


def marked_path(path: Path, result: dict) -> str:
    relative = result.get("marked_file") or f"marked/{path.stem}-marked.pdf"
    return rel(path.parent / relative)


def detail_state(slug: str, invoice_id: str) -> dict:
    path = result_path(slug, invoice_id)
    stored = load_json(path) or {}
    result = record_for_display(stored or None)
    row = None
    if is_confirmed(result):
        types = {t["id"]: t.get("name", t["id"]) for t in load_config(slug)["invoice_types"]}
        row = summary_row(result, types)
    candidate = stored.get("pending_recheck")
    if candidate:
        candidate = candidate | {"result": record_for_display(candidate["result"])}
    return {"result": result, "revision": revision(result), "candidate": candidate,
            "confirmed_row": row, "marked_pdf": marked_path(path, result) if result else None}


def require_revision(result: dict | None, expected: str | None) -> None:
    if not expected or expected != revision(result):
        raise WorkspaceError("This invoice changed. Reload it and review the current version before saving.")


def archive_confirmation(path: Path, previous: dict) -> None:
    archived = path.parent / "archive" / path.stem / f"{revision(previous)}.json"
    if not archived.exists():
        save_json(archived, record_for_display(previous))


def publish(slug: str, invoice_id: str, result: dict, previous: dict,
            *, stage: bool = False) -> str:
    """Render a new version first, then publish one atomic JSON pointer."""
    path = result_path(slug, invoice_id)
    version = uuid4().hex
    out = path.parent / "marked" / invoice_id / version
    result["revision"] = version
    result["marked_file"] = (out / f"{invoice_id}-marked.pdf").relative_to(path.parent).as_posix()
    try:
        draw(slug, invoice_id, result=result, out_dir=out, save_pages=False)
        if stage:
            pending = {"revision": version, "result": result}
            save_json(path, previous | {"pending_recheck": pending})
        else:
            if is_confirmed(previous):
                archive_confirmation(path, previous)
                if previous.get("pending_recheck"):
                    result["pending_recheck"] = previous["pending_recheck"]
            save_json(path, result)
    except Exception:
        # Only this attempt owns this newly allocated directory.
        if out.exists():
            shutil.rmtree(out)
        raise
    return marked_path(path, result)


def save(slug: str, invoice_id: str, draft: dict) -> dict:
    if not isinstance(draft, dict):
        raise WorkspaceError("The draft must be an object.")
    unknown = set(draft) - ALLOWED_KEYS
    if unknown:
        raise WorkspaceError(f"Unknown keys in the draft: {sorted(unknown)}.")
    source = invoice_path(slug, invoice_id)
    incoming = {"invoice": invoice_id, "file": source.name,
                "display_file": invoice_display_name(slug, invoice_id, source=source), "checked_at": now_iso(), "checked_by": "assistant",
                "fields": {}, "visual": {}, "questions": [], "summary": ""} | draft
    with review_lock(slug):
        previous = load_json(result_path(slug, invoice_id)) or {}
        checked = checked_result(slug, incoming)
        staged = is_confirmed(previous)
        pdf = publish(slug, invoice_id, checked, previous, stage=staged)
        failures = [o["name"] for o in checked["rule_results"] if o["outcome"] == "failed"]
        action = "recheck ready for review" if staged else "invoice checked"
        log(slug, "assistant", action, {"invoice": invoice_id, "status": checked["status"], "failed": failures})
    return {"invoice": invoice_id, "status": checked["status"], "rules_checked": checked["rules_checked"],
            "failed": failures, "unclear": [o["name"] for o in checked["rule_results"] if o["outcome"] == "unclear"],
            "staged": staged, "marked_pdf": pdf}


def recalculate(slug: str, invoice_id: str) -> dict:
    """The rules CLI uses the same publication boundary as a full recheck."""
    with review_lock(slug):
        path = result_path(slug, invoice_id)
        previous = load_json(path)
        if not previous:
            raise WorkspaceError(f"There is no result for '{invoice_id}' yet.")
        checked = checked_result(slug, record_for_display(previous))
        staged = is_confirmed(previous)
        publish(slug, invoice_id, checked, previous, stage=staged)
        return checked


def save_review(slug: str, invoice_id: str, body: dict) -> dict:
    with review_lock(slug):
        path = result_path(slug, invoice_id)
        previous = load_json(path)
        if not previous:
            raise WorkspaceError("This invoice has not been checked yet.")
        require_revision(previous, body.get("revision"))
        result = record_for_display(previous)
        if "ai_original" not in result:
            result["ai_original"] = {k: deepcopy(v) for k, v in result.items()
                                     if k not in ("review", "revision", "marked_file")}
        config = load_config(slug)
        known_fields = {f["name"] for f in config["fields"] if f["type_id"] == result.get("type_id")}
        corrections = {k: v for k, v in (body.get("fields") or {}).items() if k in known_fields}
        known_rules = {o["rule_id"] for o in result.get("rule_results", [])}
        known_rules.discard(DUPLICATE_RULE)
        decisions = body.get("rules", {})
        # Older clients submit only decisions. Preserve reasons while that decision stays the same.
        previous_review = result.get("review") or {}
        if not isinstance(decisions, dict):
            raise WorkspaceError("Finding decisions must be keyed by rule.")
        if "rule_reasons" in body:
            reasons = body["rule_reasons"]
        else:
            reasons = {k: v for k, v in (previous_review.get("rule_reasons") or {}).items()
                       if decisions.get(k) == (previous_review.get("rules") or {}).get(k)}
        if not isinstance(reasons, dict):
            raise WorkspaceError("Finding reasons must be keyed by rule.")
        if any(k not in known_rules or v not in RULE_OUTCOMES for k, v in decisions.items()):
            raise WorkspaceError("Choose a listed outcome for each editable finding.")
        if any(k not in known_rules or not isinstance(v, str) for k, v in reasons.items()):
            raise WorkspaceError("Enter a text reason for an editable finding.")
        reasons = {k: v.strip() for k, v in reasons.items() if v.strip()}
        previous_decisions = previous_review.get("rules") or {}
        findings = {item["rule_id"]: item for item in result.get("rule_results", [])}
        for key, decision in decisions.items():
            automatic = findings[key].get("check_outcome", findings[key].get("ai_outcome", findings[key]["outcome"]))
            if ({automatic, decision} == {"passed", "failed"} and not reasons.get(key)
                    and (previous_decisions.get(key) != decision or (previous_review.get("rule_reasons") or {}).get(key))):
                raise WorkspaceError(f"Explain why you changed the decision for {findings[key].get('name', key)}.")
        evidence = body.get("evidence", previous_review.get("evidence", {}))
        if not isinstance(evidence, dict) or set(evidence) - {"fields", "rules"}:
            raise WorkspaceError("Evidence locations must be grouped by field or rule.")
        for group, known in (("fields", known_fields), ("rules", known_rules)):
            locations = evidence.get(group, {})
            if not isinstance(locations, dict):
                raise WorkspaceError("Evidence locations must be keyed by field or rule.")
            for key, location in locations.items():
                if key not in known or not isinstance(location, dict):
                    raise WorkspaceError("This evidence location does not belong to the invoice.")
                box, page = location.get("box"), location.get("page")
                if (type(page) is not int or page < 1 or not isinstance(box, list) or len(box) != 4
                        or any(type(v) not in (int, float) for v in box)
                        or not (0 <= box[0] < box[2] <= 1 and 0 <= box[1] < box[3] <= 1)):
                    raise WorkspaceError("Select a valid location on an invoice page.")
        status = body.get("status")
        if status not in ("draft", "confirmed"):
            raise WorkspaceError("Choose Save draft or Confirm review.")
        who = body.get("by") or "staff"
        result["review"] = {"fields": corrections, "rules": decisions, "rule_reasons": reasons, "status": status,
                            "by": who, "at": now_iso(), "note": body.get("note", ""), "evidence": evidence}
        result = checked_result(slug, result)
        staged = is_confirmed(previous) and status == "draft"
        publish(slug, invoice_id, result, previous, stage=staged)
        log(slug, who, "review saved", {
            "invoice": invoice_id, "status": status, "staged": staged,
            "corrected fields": {k: {"assistant read": (result["ai_original"].get("fields", {}).get(k) or {}).get("value"),
                                     "reviewer": v} for k, v in corrections.items()},
            "changed rule outcomes": decisions, "finding reasons": reasons, "before": (previous.get("review") or {}).get("status")})
        tip = (body.get("learning") or "").strip()
        if tip:
            file = project_dir(slug) / "learnings.json"
            learnings = load_json(file, [])
            learnings.append({"id": f"L{len(learnings) + 1:03d}", "text": tip, "type_id": result["type_id"],
                              "source_invoice": invoice_id, "created": now_iso(), "active": True})
            save_json(file, learnings)
            log(slug, who, "learning saved", {"text": tip, "invoice": invoice_id})
        return record_for_display(result)


def accept_recheck(slug: str, invoice_id: str, body: dict) -> dict:
    with review_lock(slug):
        path = result_path(slug, invoice_id)
        previous = load_json(path) or {}
        require_revision(previous, body.get("revision"))
        pending = previous.get("pending_recheck")
        if not pending or pending["revision"] != body.get("candidate_revision"):
            raise WorkspaceError("The proposed result changed. Reload it and compare again.")
        result = pending["result"]
        who = body.get("by") or "staff"
        if "ai_original" not in result:
            result["ai_original"] = {k: deepcopy(v) for k, v in result.items()
                                     if k not in ("review", "revision", "marked_file")}
        result["review"] = (result.get("review") or {"fields": {}, "rules": {}}) | {
            "status": "confirmed", "by": who, "at": now_iso()}
        # Accept exactly the candidate the reviewer saw, with its existing PDF.
        result["revision"] = uuid4().hex
        archive_confirmation(path, previous)
        save_json(path, result)
        log(slug, who, "recheck accepted", {"invoice": invoice_id, "previous revision": revision(previous),
                                           "accepted candidate": pending["revision"]})
        return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["save"])
    parser.add_argument("invoice")
    parser.add_argument("draft")
    args = parser.parse_args()
    try:
        draft = json.loads(Path(args.draft).read_text(encoding="utf-8"))
        print_json(save(current_project(), args.invoice, draft))
    except json.JSONDecodeError as error:
        print(f"Error: the draft is not valid JSON ({error}).", file=sys.stderr)
        return 1
    except WorkspaceError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
