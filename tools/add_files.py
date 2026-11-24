"""Add files supplied in chat to the selected project.

Usage:
  ./.tools/uv run tools/add_files.py invoice <file> [<file> ...]
  ./.tools/uv run tools/add_files.py guideline <file> [<file> ...]
"""
from __future__ import annotations

import argparse
import base64
import sys
from contextlib import nullcontext
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from server import GUIDELINE_SUFFIXES, INVOICE_SUFFIXES, save_upload
from common import WorkspaceError, current_project, log, print_json, project_dir
from review_lock import review_lock


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=("invoice", "guideline"))
    parser.add_argument("files", nargs="+", type=Path)
    args = parser.parse_args()
    try:
        slug = current_project()
        folder = project_dir(slug) / ("invoices" if args.kind == "invoice" else "guidelines")
        allowed = INVOICE_SUFFIXES if args.kind == "invoice" else GUIDELINE_SUFFIXES
        added, errors = [], []
        for path in args.files:
            try:
                if path.stat().st_size > 20 * 1024 * 1024:
                    raise WorkspaceError("The file exceeds 20 MB.")
                data = base64.b64encode(path.read_bytes()).decode("ascii")
                with review_lock(slug) if args.kind == "guideline" else nullcontext():
                    upload = save_upload(folder, {"name": path.name, "data": data}, allowed,
                                         slug if args.kind == "invoice" else None)
                    log(slug, "assistant", f"{args.kind} added", upload)
                added.append(upload)
            except (OSError, WorkspaceError) as error:
                errors.append({"file": path.name, "error": str(error)})
        print_json({"added": added, "errors": errors})
        return 1 if errors else 0
    except WorkspaceError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
