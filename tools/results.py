"""Save what the assistant read from an invoice, then run the rules and draw the marks.

Usage:
  python tools/results.py save <invoice> <draft.json> [--set evaluation]

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
import json
import sys
from pathlib import Path

from checks import run as run_checks
from common import WorkspaceError, current_project, invoice_path, load_json, log, now_iso, print_json, result_path, save_json
from marks import draw

ALLOWED_KEYS = {"type_id", "type_reason", "fields", "visual", "questions", "summary"}


def save(slug: str, invoice_id: str, draft: dict, which: str) -> dict:
    unknown = set(draft) - ALLOWED_KEYS
    if unknown:
        raise WorkspaceError(f"Unknown keys in the draft: {sorted(unknown)}.")
    source = invoice_path(slug, invoice_id, which)
    path = result_path(slug, invoice_id, which)
    previous = load_json(path, {}) or {}
    result = {"invoice": invoice_id, "file": source.name, "checked_at": now_iso(), "checked_by": "assistant",
              "fields": {}, "visual": {}, "questions": [], "summary": ""}
    result.update(draft)
    if previous.get("review"):
        result["previous_review"] = previous["review"]
    save_json(path, result)
    try:
        checked = run_checks(slug, invoice_id, which)
    except WorkspaceError:
        if previous:
            save_json(path, previous)
        else:
            path.unlink()
        raise
    marked = draw(slug, invoice_id, which)
    failed = [o["name"] for o in checked["rule_results"] if o["outcome"] == "failed"]
    if which == "invoices":
        log(slug, "assistant", "invoice checked", {"invoice": invoice_id, "status": checked["status"], "failed": failed})
    return {"invoice": invoice_id, "status": checked["status"], "failed": failed,
            "unclear": [o["name"] for o in checked["rule_results"] if o["outcome"] == "unclear"],
            "marked_pdf": marked["pdf"]}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["save"])
    parser.add_argument("invoice")
    parser.add_argument("draft")
    parser.add_argument("--set", dest="which", default="invoices", choices=["invoices", "evaluation"])
    args = parser.parse_args()
    try:
        draft = json.loads(Path(args.draft).read_text(encoding="utf-8"))
        print_json(save(current_project(), args.invoice, draft, args.which))
    except json.JSONDecodeError as error:
        print(f"Error: the draft is not valid JSON ({error}).", file=sys.stderr)
        return 1
    except WorkspaceError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
