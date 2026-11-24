"""Turn invoice files into page images the assistant can look at.

Usage:
  ./.tools/uv run tools/pages.py pending     # invoices without a result yet
  ./.tools/uv run tools/pages.py render <invoice>
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import shutil
import tempfile
import sys
from pathlib import Path

import pypdfium2
from PIL import Image

from common import (
    PDFIUM_LOCK, WorkspaceError, ambiguous_invoice_ids, current_project, invoice_files, invoice_path, print_json, rel, result_path, work_dir,
)

DPI = 200


def render(slug: str, invoice_id: str, expected_digest: str | None = None) -> list[dict]:
    source = invoice_path(slug, invoice_id)
    root = work_dir(slug, invoice_id) / "page-sets"
    root.mkdir(parents=True, exist_ok=True)
    if expected_digest:
        if not isinstance(expected_digest, str) or len(expected_digest) != 64 or any(c not in "0123456789abcdef" for c in expected_digest):
            raise WorkspaceError("The saved invoice source identifier is invalid.")
        existing = root / expected_digest
        if existing.is_dir():
            return page_metadata(existing)
    content = source.read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    if expected_digest and expected_digest != digest:
        raise WorkspaceError("The original document pages are unavailable because the invoice file changed. Restore the original file to view this result's evidence.")
    out = root / digest
    if out.is_dir():
        return page_metadata(out)
    images: list[Image.Image] = []
    if source.suffix.lower() == ".pdf":
        # PDFium is not safe for concurrent calls within a process.
        with PDFIUM_LOCK:
            document = pypdfium2.PdfDocument(content)
            try:
                for index in range(len(document)):
                    images.append(document[index].render(scale=DPI / 72).to_pil().convert("RGB"))
            finally:
                document.close()
    else:
        images.append(Image.open(io.BytesIO(content)).convert("RGB"))
    if not images:
        raise WorkspaceError("The invoice has no readable pages.")
    temporary = Path(tempfile.mkdtemp(prefix=".render-", dir=root))
    try:
        for number, image in enumerate(images, start=1):
            image.save(temporary / f"page-{number}.png")
        (temporary / "manifest.json").write_text(json.dumps({"page_count": len(images)}), encoding="utf-8")
        try:
            os.rename(temporary, out)
        except OSError:
            if not out.is_dir():
                raise
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return page_metadata(out)


def page_metadata(folder: Path) -> list[dict]:
    try:
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        count = manifest["page_count"]
        if not isinstance(count, int) or isinstance(count, bool) or count < 1:
            raise ValueError("invalid page count")
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise WorkspaceError("The stored page images are incomplete. Restore the original invoice to repair them.") from error
    files = sorted((p for p in folder.glob("page-*.png") if p.stem[5:].isdecimal()),
                   key=lambda p: int(p.stem[5:]))
    if len(files) != count:
        raise WorkspaceError("The stored page images are incomplete. Restore the original invoice to repair them.")
    pages = []
    for number, path in enumerate(files, start=1):
        if path.name != f"page-{number}.png":
            raise WorkspaceError("The stored page images are incomplete. Restore the original invoice to repair them.")
        with Image.open(path) as image:
            pages.append({"page": number, "path": rel(path), "width": image.width, "height": image.height})
    if not pages:
        raise WorkspaceError("The stored invoice has no readable pages.")
    return pages


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["pending", "render"])
    parser.add_argument("invoice", nargs="?")
    args = parser.parse_args()
    try:
        slug = current_project()
        if args.command == "pending":
            files = invoice_files(slug)
            ambiguous = ambiguous_invoice_ids(slug)
            pending = [i for i in files if i not in ambiguous and not result_path(slug, i).exists()]
            print_json({"project": slug, "set": "invoices", "pending": pending, "total": len(files)})
        else:
            if not args.invoice:
                raise WorkspaceError("Say which invoice to render.")
            print_json({"invoice": args.invoice, "pages": render(slug, args.invoice)})
    except WorkspaceError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
