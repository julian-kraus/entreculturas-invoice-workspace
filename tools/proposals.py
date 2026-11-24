"""Changes the assistant proposes. People approve or reject them on the workspace page.

Usage:
  ./.tools/uv run tools/proposals.py corrections        # what reviewers corrected, for suggesting changes
  ./.tools/uv run tools/proposals.py propose <draft.json>
  ./.tools/uv run tools/proposals.py list               # proposals still waiting

The draft is a list of changes to existing items:
[
  {
    "kind": "field",                   # field, invoice_type or rule
    "target": "VIA_002",               # the item's id
    "changes": {"hint": "New text for how to find this value"},
    "reason": "Reviewers corrected this value 3 times: the funds request number was expected.",
    "evidence": ["a3693-travel-fuel", "u0204-taxi"]
  }
]
New rules are proposed with tools/rules.py instead.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from review_lock import review_lock
from common import (
    WorkspaceError, current_project, load_config, load_json, log, now_iso, print_json, project_dir, result_path, save_json,
)

EDITABLE = {
    "field": ("fields.json", {"label", "hint", "required", "kind"}),
    "invoice_type": ("invoice_types.json", {"name", "description", "what_to_look_for"}),
    "rule": ("rules.json", {"name", "description", "hint", "severity", "value", "field"}),
}


def path(slug: str) -> Path:
    return project_dir(slug) / "proposals.json"


def pending(slug: str) -> list[dict]:
    return [p for p in load_json(path(slug), []) if p.get("status") == "pending"]


def propose(slug: str, drafts: list[dict], who: str = "assistant") -> list[str]:
    with review_lock(slug):
        return _propose(slug, drafts, who)


def _propose(slug: str, drafts: list[dict], who: str = "assistant") -> list[str]:
    proposals = load_json(path(slug), [])
    problems, added = [], []
    for index, draft in enumerate(drafts, start=1):
        kind, target = draft.get("kind"), draft.get("target")
        label = f"Change {index} ({kind} {target})"
        if kind not in EDITABLE:
            problems.append(f"{label}: kind must be field, invoice_type or rule.")
            continue
        filename, allowed = EDITABLE[kind]
        items = {i["id"]: i for i in load_json(project_dir(slug) / filename, [])}
        if target not in items:
            problems.append(f"{label}: there is no {kind} with id '{target}'.")
            continue
        changes = draft.get("changes") or {}
        unknown = set(changes) - allowed
        if not changes or unknown:
            problems.append(f"{label}: you can change {sorted(allowed)}; got {sorted(changes) or 'nothing'}.")
            continue
        if not str(draft.get("reason", "")).strip():
            problems.append(f"{label}: say why, in one plain sentence.")
            continue
        evidence = draft.get("evidence", [])
        if not isinstance(evidence, list) or any(not isinstance(item, str) for item in evidence):
            problems.append(f"{label}: evidence must be a list of reviewed invoice IDs.")
            continue
        for invoice_id in evidence:
            try:
                result = load_json(result_path(slug, invoice_id), {}) or {}
            except WorkspaceError:
                result = {}
            if (result.get("review") or {}).get("status") != "confirmed":
                problems.append(f"{label}: confirm the review of '{invoice_id}' before using it as evidence.")
        before = {k: items[target].get(k) for k in changes}
        if before == changes:
            problems.append(f"{label}: this is already the current value.")
            continue
        number = len(proposals) + len(added) + 1
        proposal = {"id": f"C{number:03d}", "kind": kind, "target": target,
                    "target_name": items[target].get("label") or items[target].get("name") or target,
                    "before": before, "after": changes, "reason": draft["reason"].strip(),
                    "evidence": [str(e) for e in draft.get("evidence", [])][:10],
                    "status": "pending", "proposed_by": who, "created": now_iso()}
        added.append(proposal)
    if problems:
        raise WorkspaceError("Fix these before proposing:\n- " + "\n- ".join(problems))
    save_json(path(slug), proposals + added)
    log(slug, who, "changes proposed", {"proposals": [p["id"] for p in added]})
    return [p["id"] for p in added]


def decide(slug: str, proposal_id: str, approve: bool, who: str = "staff", *,
           expected: dict | None = None, edits: dict | None = None) -> dict:
    proposals = load_json(path(slug), [])
    proposal = next((p for p in proposals if p["id"] == proposal_id), None)
    if not proposal or proposal.get("status") != "pending":
        raise WorkspaceError("This proposal is no longer waiting for a decision.")
    if expected is not None and proposal != expected:
        raise WorkspaceError("This proposal changed since you opened it.")
    applied = {**proposal["after"], **(edits or {})}
    if edits:
        if not approve or not edits.keys() <= proposal["after"].keys():
            raise WorkspaceError("Edit only the values included in the proposal.")
        for key, value in edits.items():
            if key == "required" and not isinstance(value, bool):
                raise WorkspaceError("Choose whether this field is required.")
            if key == "kind" and value not in ("text", "date", "amount"):
                raise WorkspaceError("Choose a valid field kind.")
            if key == "severity" and value not in ("warning", "error"):
                raise WorkspaceError("Choose a valid rule severity.")
            if key in {"name", "label"} and (not isinstance(value, str) or not value.strip()):
                raise WorkspaceError("Enter a name before confirming.")
            original = proposal["after"][key]
            if original is not None and type(original) is not type(value):
                raise WorkspaceError(f"Keep the value type of {key}.")
    if approve:
        filename, _ = EDITABLE[proposal["kind"]]
        file = project_dir(slug) / filename
        items = load_json(file, [])
        item = next((i for i in items if i["id"] == proposal["target"]), None)
        if item is None:
            raise WorkspaceError("The item this proposal changes no longer exists.")
        current = {k: item.get(k) for k in proposal["before"]}
        if current != proposal["before"]:
            raise WorkspaceError("Someone changed this item after the proposal was made. Reject it and ask for a new one.")
        item.update(applied)
        if edits:
            proposal["reviewed_after"] = applied
        save_json(file, items)
    proposal.update({"status": "approved" if approve else "rejected", "decided_by": who, "decided_at": now_iso()})
    save_json(path(slug), proposals)
    log(slug, who, f"proposal {'approved' if approve else 'rejected'}", {
        "proposal": proposal_id, "what": f"{proposal['kind']} {proposal['target_name']}",
        "before": proposal["before"], "after": applied, "reason": proposal["reason"],
        **({"proposed": proposal["after"]} if edits else {})})
    return proposal


def corrections(slug: str) -> dict:
    """Collect review corrections, project tips and pending proposals."""
    config = load_config(slug)
    labels = {(f["type_id"], f["name"]): (f["id"], f["label"]) for f in config["fields"]}
    results_dir = project_dir(slug) / "results"
    items = []
    for result_file in sorted(results_dir.glob("*.json")) if results_dir.exists() else []:
        result = load_json(result_file, {})
        review = result.get("review") or {}
        if review.get("status") != "confirmed":
            continue
        original = (result.get("ai_original") or result).get("fields", {})
        for name, value in (review.get("fields") or {}).items():
            field_id, label = labels.get((result.get("type_id"), name), (None, name))
            items.append({"invoice": result_file.stem, "type_id": result.get("type_id"), "field_id": field_id,
                          "field": label, "assistant_read": (original.get(name) or {}).get("value"),
                          "reviewer": value, "assistant_note": (original.get(name) or {}).get("note")})
        decisions = review.get("rules") or {}
        reasons = review.get("rule_reasons") or {}
        for rule_id in sorted(decisions.keys() | reasons.keys()):
            items.append({"invoice": result_file.stem, "type_id": result.get("type_id"), "rule_id": rule_id,
                          "reviewer_outcome": decisions.get(rule_id), "reviewer_reason": reasons.get(rule_id)})
    return {"corrections": items, "learnings": config["learnings"],
            "pending_proposals": pending(slug)}


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in {"corrections", "propose", "list"}:
        print(__doc__, file=sys.stderr)
        return 2
    try:
        slug = current_project()
        if sys.argv[1] == "corrections":
            print_json(corrections(slug))
        elif sys.argv[1] == "list":
            print_json(pending(slug))
        else:
            if len(sys.argv) != 3:
                raise WorkspaceError("Give the draft file.")
            drafts = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
            if not isinstance(drafts, list):
                raise WorkspaceError("The draft must be a list of changes.")
            print_json({"proposed": propose(slug, drafts)})
    except json.JSONDecodeError as error:
        print(f"Error: the draft is not valid JSON ({error}).", file=sys.stderr)
        return 1
    except WorkspaceError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
