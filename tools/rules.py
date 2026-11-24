"""Add proposed rules. People confirm or reject them on the workspace page.

Usage:
  ./.tools/uv run tools/rules.py propose <draft.json>

The draft is a list of rules:
[
  {
    "type_id": "VOLUNTARIOS",              # or "ALL" for every invoice type
    "name": "receipt signed by the volunteer",
    "check": "visual",                    # visual, required, regex, range, enum or date_in_period
    "field": null,                        # field name for non-visual checks
    "value": "",                          # pattern, "min,max" or "a,b,c" where the check needs it
    "severity": "error",                  # error or warning
    "description": "Plain sentence a reviewer understands.",
    "hint": "Where to look on the document.",       # required
    "reason": "Why this rule: what in the guideline asks for it.",
    "source": "Guía AEXCID 2025.pdf, page 14, section 4.2"
  }
]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from review_lock import review_lock
from common import WorkspaceError, current_project, load_config, load_json, log, now_iso, print_json, project_dir, save_json

CHECKS = {"visual", "required", "regex", "range", "enum", "date_in_period"}


def propose(slug: str, drafts: list[dict]) -> list[str]:
    with review_lock(slug):
        return _propose(slug, drafts)


def _propose(slug: str, drafts: list[dict]) -> list[str]:
    config = load_config(slug)
    type_ids = {t["id"] for t in config["invoice_types"]} | {"ALL"}
    fields = {(f["type_id"], f["name"]) for f in config["fields"]}
    path = project_dir(slug) / "rules.json"
    rules = load_json(path, [])
    taken = {r["id"] for r in rules}
    added, problems = [], []
    for index, draft in enumerate(drafts, start=1):
        label = f"Rule {index} ({draft.get('name', 'no name')})"
        if draft.get("type_id") not in type_ids:
            problems.append(f"{label}: type_id must be one of {sorted(type_ids)}.")
        if draft.get("check") not in CHECKS:
            problems.append(f"{label}: check must be one of {sorted(CHECKS)}.")
        if draft.get("check") != "visual" and draft.get("type_id") != "ALL" and (draft.get("type_id"), draft.get("field")) not in fields:
            problems.append(f"{label}: field '{draft.get('field')}' does not exist for this invoice type.")
        if not str(draft.get("source", "")).strip():
            problems.append(f"{label}: every proposed rule needs a source (document and page).")
        if not str(draft.get("description", "")).strip():
            problems.append(f"{label}: add a plain description.")
        if not str(draft.get("hint", "")).strip():
            problems.append(f"{label}: say where to look on the document (hint).")
    if problems:
        raise WorkspaceError("Fix these before proposing:\n- " + "\n- ".join(problems))
    number = 1
    for draft in drafts:
        while f"P{number:03d}" in taken:
            number += 1
        rule_id = f"P{number:03d}"
        taken.add(rule_id)
        rules.append({
            "id": rule_id, "type_id": draft["type_id"], "name": draft.get("name", rule_id), "check": draft["check"],
            "field": draft.get("field"), "value": draft.get("value", ""), "severity": draft.get("severity", "error"),
            "description": draft["description"], "hint": draft.get("hint", ""), "source": draft["source"],
            "status": "proposed", "enabled": True, "proposed_by": "assistant", "proposed_at": now_iso(),
            "reason": draft.get("reason", ""),
        })
        added.append(rule_id)
    save_json(path, rules)
    log(slug, "assistant", "rules proposed", {"rules": added})
    return added


def main() -> int:
    if len(sys.argv) != 3 or sys.argv[1] != "propose":
        print(__doc__, file=sys.stderr)
        return 2
    try:
        drafts = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
        if not isinstance(drafts, list):
            raise WorkspaceError("The draft must be a list of rules.")
        print_json({"proposed": propose(current_project(), drafts)})
    except json.JSONDecodeError as error:
        print(f"Error: the draft is not valid JSON ({error}).", file=sys.stderr)
        return 1
    except WorkspaceError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
