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
    WorkspaceError, ambiguous_invoice_ids, current_project, invoice_display_name, invoice_path, load_config, load_json, log, now_iso, print_json,
    project_dir, rel, result_path, save_json,
)
from marks import draw
from pages import render
from proposals import pending as pending_proposals
from report import summary_row
from review_lock import review_lock

class ReviewConflict(WorkspaceError):
    """A result or pending change no longer matches the version seen."""


def require_inbox_handled(slug: str) -> None:
    """Call under the project lock before beginning or publishing a check."""
    rules = load_json(project_dir(slug) / "rules.json", [])
    count = sum(rule.get("status") == "proposed" for rule in rules) + len(pending_proposals(slug))
    if count:
        raise WorkspaceError(
            f"The project Inbox has {count} item{'s' if count != 1 else ''} awaiting a decision. "
            "Confirm or reject every item in Project setup → Inbox before checking invoices."
        )


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
        candidate = candidate | {"origin": candidate.get("origin", "unknown"), "result": record_for_display(candidate["result"])}
    return {"result": result, "revision": revision(result), "candidate": candidate,
            "confirmed_row": row, "marked_pdf": marked_path(path, result) if result else None}


def require_revision(result: dict | None, expected: str | None) -> None:
    if not expected or expected != revision(result):
        raise ReviewConflict("This invoice changed. Reload it and review the current version before saving.")


def archive_confirmation(path: Path, previous: dict) -> None:
    archived = path.parent / "archive" / path.stem / f"{revision(previous)}.json"
    if not archived.exists():
        save_json(archived, record_for_display(previous))


def reconcile_effects(slug: str, invoice_id: str) -> None:
    """Apply committed review side effects once; called while holding the project lock."""
    path = result_path(slug, invoice_id)
    stored = load_json(path) or {}
    effects = stored.get("_pending_effects") or []
    if not effects:
        return
    history = project_dir(slug) / "history.jsonl"
    seen = set()
    if history.exists():
        for line in history.read_text(encoding="utf-8").splitlines():
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            operation = (entry.get("detail") or {}).get("operation_id")
            if operation:
                seen.add(operation)
    for effect in effects:
        op_id = effect["id"]
        if effect.get("tip"):
            file = project_dir(slug) / "learnings.json"
            learnings = load_json(file, [])
            if not any(item.get("operation_id") == op_id for item in learnings):
                learnings.append({"id": f"L{len(learnings) + 1:03d}", "text": effect["tip"],
                                  "type_id": effect["type_id"], "source_invoice": invoice_id,
                                  "created": effect["at"], "active": True, "operation_id": op_id})
                save_json(file, learnings)
        if op_id not in seen:
            log(slug, effect["who"], effect["action"], effect["detail"] | {"operation_id": op_id})
            seen.add(op_id)
    save_json(path, {key: value for key, value in stored.items() if key != "_pending_effects"})


def finish_effects(slug: str, invoice_id: str) -> None:
    # The result pointer is already committed. A later mutation can retry this safely.
    try:
        reconcile_effects(slug, invoice_id)
    except OSError:
        pass


def publish(slug: str, invoice_id: str, result: dict, previous: dict,
            *, stage: bool = False, origin: str | None = None, effects: list[dict] | None = None) -> str:
    """Render a new version first, then publish one atomic JSON pointer."""
    path = result_path(slug, invoice_id)
    version = uuid4().hex
    out = path.parent / "marked" / invoice_id / version
    result["revision"] = version
    result["marked_file"] = (out / f"{invoice_id}-marked.pdf").relative_to(path.parent).as_posix()
    try:
        draw(slug, invoice_id, result=result, out_dir=out, save_pages=False)
        if stage:
            pending = {"revision": version, "origin": origin, "result": result}
            saved = previous | {"pending_recheck": pending}
            if effects:
                saved["_pending_effects"] = (previous.get("_pending_effects") or []) + effects
            save_json(path, saved)
        else:
            if is_confirmed(previous):
                archive_confirmation(path, previous)
            if effects:
                result["_pending_effects"] = (previous.get("_pending_effects") or []) + effects
            save_json(path, result)
    except Exception:
        # Only this attempt owns this newly allocated directory.
        if out.exists():
            shutil.rmtree(out)
        raise
    return marked_path(path, result)


def input_digests(slug: str, invoice_id: str) -> dict:
    """Fingerprint the source and checking configuration before reading."""
    source = invoice_path(slug, invoice_id)
    source_digest = hashlib.sha256(source.read_bytes()).hexdigest()
    config = load_config(slug)
    relevant = {key: config.get(key) for key in ("project", "invoice_types", "fields", "rules", "learnings")}
    data = json.dumps(relevant, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    return {"source_digest": source_digest, "config_digest": hashlib.sha256(data).hexdigest()}


def require_original_source(slug: str, invoice_id: str, result: dict) -> None:
    """Avoid applying old evidence to a replacement document."""
    expected = result.get("source_digest")
    if expected and hashlib.sha256(invoice_path(slug, invoice_id).read_bytes()).hexdigest() != expected:
        raise ReviewConflict("The invoice file has changed since this result was checked. Recheck the current file before saving its review.")


def inspect(slug: str, invoice_id: str) -> dict:
    with review_lock(slug):
        require_inbox_handled(slug)
        if invoice_id in ambiguous_invoice_ids(slug):
            raise ReviewConflict("Multiple invoice files share this name and their saved result is unreadable. Resolve the source before checking.")
        reconcile_effects(slug, invoice_id)
        detail = detail_state(slug, invoice_id)
        return {
            "revision": detail["revision"],
            "candidate": detail["candidate"],
            "review_status": ((detail["result"] or {}).get("review") or {}).get("status"),
            **input_digests(slug, invoice_id),
        }


def save(slug: str, invoice_id: str, draft: dict, *, intent: str = "initial",
         expected_revision: str | None = None, source_digest: str | None = None,
         config_digest: str | None = None) -> dict:
    if not isinstance(draft, dict):
        raise WorkspaceError("The draft must be an object.")
    unknown = set(draft) - ALLOWED_KEYS
    if unknown:
        raise WorkspaceError(f"Unknown keys in the draft: {sorted(unknown)}.")
    if intent not in ("initial", "recheck"):
        raise WorkspaceError("Choose initial or recheck.")
    with review_lock(slug):
        require_inbox_handled(slug)
        if invoice_id in ambiguous_invoice_ids(slug):
            raise ReviewConflict("Multiple invoice files share this name and their saved result is unreadable. Resolve the source before checking.")
        reconcile_effects(slug, invoice_id)
        source = invoice_path(slug, invoice_id)
        previous = load_json(result_path(slug, invoice_id)) or {}
        if intent == "initial":
            if previous:
                raise ReviewConflict("This invoice already has a saved result. Skip it or request a recheck.")
        else:
            require_revision(previous, expected_revision)
            if previous.get("pending_recheck"):
                raise ReviewConflict("A pending change already exists. Review it before rechecking.")
            if (previous.get("review") or {}).get("status") == "draft":
                raise ReviewConflict("A staff draft already exists. Finish it before rechecking.")
        current = input_digests(slug, invoice_id)
        if source_digest is not None and source_digest != current["source_digest"]:
            raise ReviewConflict("The invoice file changed. Read it again before saving.")
        if config_digest is not None and config_digest != current["config_digest"]:
            raise ReviewConflict("The project setup changed. Reload it and check the invoice again.")
        # The page cache can predate an externally replaced source file. Refresh
        # it before producing this check's marked PDF, and verify the file again.
        render(slug, invoice_id)
        if hashlib.sha256(source.read_bytes()).hexdigest() != current["source_digest"]:
            raise ReviewConflict("The invoice file changed. Read it again before saving.")
        incoming = {"invoice": invoice_id, "file": source.name,
                    "display_file": invoice_display_name(slug, invoice_id, source=source),
                    "checked_at": now_iso(), "checked_by": "assistant",
                    "source_digest": current["source_digest"],
                    "fields": {}, "visual": {}, "questions": [], "summary": ""} | draft
        checked = checked_result(slug, incoming)
        staged = is_confirmed(previous)
        failures = [o["name"] for o in checked["rule_results"] if o["outcome"] == "failed"]
        effect = {"id": uuid4().hex, "who": "assistant",
                  "action": "recheck ready for review" if staged else "invoice checked",
                  "detail": {"invoice": invoice_id, "status": checked["status"], "failed": failures}}
        pdf = publish(slug, invoice_id, checked, previous, stage=staged,
                      origin="assistant_recheck", effects=[effect])
        finish_effects(slug, invoice_id)
    return {"invoice": invoice_id, "status": checked["status"], "rules_checked": checked["rules_checked"],
            "failed": failures, "unclear": [o["name"] for o in checked["rule_results"] if o["outcome"] == "unclear"],
            "staged": staged, "marked_pdf": pdf}


def recalculate(slug: str, invoice_id: str, expected_revision: str | None = None) -> dict:
    with review_lock(slug):
        require_inbox_handled(slug)
        reconcile_effects(slug, invoice_id)
        path = result_path(slug, invoice_id)
        previous = load_json(path)
        if not previous:
            raise WorkspaceError(f"There is no result for '{invoice_id}' yet.")
        if expected_revision is not None:
            require_revision(previous, expected_revision)
        if previous.get("pending_recheck"):
            raise ReviewConflict("A pending change already exists. Review it before recalculating.")
        if (previous.get("review") or {}).get("status") == "draft":
            raise ReviewConflict("A staff draft already exists. Finish it before recalculating.")
        require_original_source(slug, invoice_id, previous)
        checked = checked_result(slug, record_for_display(previous))
        staged = is_confirmed(previous)
        publish(slug, invoice_id, checked, previous, stage=staged, origin="rule_recalculation")
        return checked


def save_review(slug: str, invoice_id: str, body: dict) -> dict:
    with review_lock(slug):
        reconcile_effects(slug, invoice_id)
        path = result_path(slug, invoice_id)
        previous = load_json(path)
        if not previous:
            raise WorkspaceError("This invoice has not been checked yet.")
        require_revision(previous, body.get("revision"))
        pending = previous.get("pending_recheck")
        candidate_revision = body.get("candidate_revision")
        if pending:
            if not candidate_revision or pending.get("revision") != candidate_revision:
                raise ReviewConflict("A pending change exists. Review it before editing this invoice.")
            if pending.get("origin") != "staff_draft":
                raise ReviewConflict("This pending change must be compared before editing.")
            result = record_for_display(pending["result"])
        else:
            if candidate_revision is not None:
                raise ReviewConflict("The pending change no longer exists. Reload this invoice.")
            result = record_for_display(previous)
        require_original_source(slug, invoice_id, result)
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
        tip = (body.get("learning") or "").strip()
        effect = {
            "id": uuid4().hex, "who": who, "action": "review saved", "at": now_iso(),
            "type_id": result["type_id"], "tip": tip,
            "detail": {
                "invoice": invoice_id, "status": status, "staged": staged,
                "corrected fields": {k: {"assistant read": (result["ai_original"].get("fields", {}).get(k) or {}).get("value"),
                                         "reviewer": v} for k, v in corrections.items()},
                "changed rule outcomes": decisions, "finding reasons": reasons,
                "before": (previous.get("review") or {}).get("status"),
            },
        }
        publish(slug, invoice_id, result, previous, stage=staged, origin="staff_draft", effects=[effect])
        finish_effects(slug, invoice_id)
        return record_for_display(result)


def accept_recheck(slug: str, invoice_id: str, body: dict) -> dict:
    with review_lock(slug):
        reconcile_effects(slug, invoice_id)
        path = result_path(slug, invoice_id)
        previous = load_json(path) or {}
        require_revision(previous, body.get("revision"))
        pending = previous.get("pending_recheck")
        if not pending or pending["revision"] != body.get("candidate_revision"):
            raise WorkspaceError("The proposed result changed. Reload it and compare again.")
        result = pending["result"]
        require_original_source(slug, invoice_id, result)
        who = body.get("by") or "staff"
        if "ai_original" not in result:
            result["ai_original"] = {k: deepcopy(v) for k, v in result.items()
                                     if k not in ("review", "revision", "marked_file")}
        result["review"] = (result.get("review") or {"fields": {}, "rules": {}}) | {
            "status": "confirmed", "by": who, "at": now_iso()}
        # Publish a new PDF whose cover reflects the accepted confirmation.
        effect = {"id": uuid4().hex, "who": who, "action": "recheck accepted",
                  "detail": {"invoice": invoice_id, "previous revision": revision(previous),
                             "accepted candidate": pending["revision"]}}
        publish(slug, invoice_id, result, previous, effects=[effect])
        finish_effects(slug, invoice_id)
        return result



def discard_candidate(slug: str, invoice_id: str, body: dict) -> dict:
    with review_lock(slug):
        reconcile_effects(slug, invoice_id)
        path = result_path(slug, invoice_id)
        previous = load_json(path) or {}
        require_revision(previous, body.get("revision"))
        pending = previous.get("pending_recheck")
        if not pending or pending.get("revision") != body.get("candidate_revision"):
            raise ReviewConflict("The pending change changed. Reload it and review again.")
        archive = path.parent / "archive" / invoice_id / "discarded" / f"{pending['revision']}.json"
        save_json(archive, pending)
        effect = {"id": uuid4().hex, "who": body.get("by") or "staff", "action": "pending change discarded",
                  "detail": {"invoice": invoice_id, "candidate revision": pending["revision"]}}
        updated = {key: value for key, value in previous.items() if key != "pending_recheck"}
        updated["_pending_effects"] = (previous.get("_pending_effects") or []) + [effect]
        save_json(path, updated)
        finish_effects(slug, invoice_id)
        return detail_state(slug, invoice_id)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["save", "inspect"])
    parser.add_argument("invoice")
    parser.add_argument("draft", nargs="?")
    parser.add_argument("--intent", choices=["initial", "recheck"], default="initial")
    parser.add_argument("--revision")
    parser.add_argument("--source-digest")
    parser.add_argument("--config-digest")
    args = parser.parse_args()
    try:
        slug = current_project()
        if args.command == "inspect":
            print_json(inspect(slug, args.invoice))
        else:
            if not args.draft:
                raise WorkspaceError("Give the draft file.")
            if not args.source_digest or not args.config_digest:
                raise WorkspaceError("Inspect the invoice first and provide both source and configuration digests.")
            draft = json.loads(Path(args.draft).read_text(encoding="utf-8"))
            print_json(save(slug, args.invoice, draft, intent=args.intent, expected_revision=args.revision,
                            source_digest=args.source_digest, config_digest=args.config_digest))
    except json.JSONDecodeError as error:
        print(f"Error: the draft is not valid JSON ({error}).", file=sys.stderr)
        return 1
    except WorkspaceError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
