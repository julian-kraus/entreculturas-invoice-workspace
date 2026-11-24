"""Turn invoice files into page images the assistant can look at.

Usage:
  ./.tools/uv run tools/pages.py pending     # invoices without a result yet
  ./.tools/uv run tools/pages.py render <invoice>
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pypdfium2
from PIL import Image

from common import (
    WorkspaceError, current_project, invoice_files, invoice_path, print_json, rel, result_path, work_dir,
)

DPI = 200


def render(slug: str, invoice_id: str) -> list[dict]:
    source = invoice_path(slug, invoice_id)
    out = work_dir(slug, invoice_id)
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("page-*.png"):
        old.unlink()
    images: list[Image.Image] = []
    if source.suffix.lower() == ".pdf":
        document = pypdfium2.PdfDocument(str(source))
        try:
            for index in range(len(document)):
                images.append(document[index].render(scale=DPI / 72).to_pil().convert("RGB"))
        finally:
            document.close()
    else:
        images.append(Image.open(source).convert("RGB"))
    pages = []
    for number, image in enumerate(images, start=1):
        path = out / f"page-{number}.png"
        image.save(path)
        pages.append({"page": number, "path": rel(path), "width": image.width, "height": image.height})
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
            pending = [i for i in files if not result_path(slug, i).exists()]
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
