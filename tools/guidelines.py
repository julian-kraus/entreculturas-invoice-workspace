"""Read funder guidelines so rules can cite the page they come from.

Usage:
  python tools/guidelines.py list
  python tools/guidelines.py text <file name> [--pages 3-7]
"""

from __future__ import annotations

import argparse
import sys

import pypdfium2

from common import WorkspaceError, current_project, print_json, project_dir


def folder(slug: str):
    return project_dir(slug) / "guidelines"


def parse_pages(text: str | None, count: int) -> list[int]:
    if not text:
        return list(range(1, count + 1))
    pages: list[int] = []
    for part in text.split(","):
        start, _, end = part.partition("-")
        first, last = int(start), int(end or start)
        pages.extend(range(max(1, first), min(count, last) + 1))
    return pages


def read_text(slug: str, name: str, pages: str | None) -> list[dict]:
    path = folder(slug) / name
    if path.parent != folder(slug) or not path.exists():
        raise WorkspaceError(f"There is no guideline file called '{name}'.")
    if path.suffix.lower() in (".txt", ".md"):
        return [{"page": 1, "text": path.read_text(encoding="utf-8")}]
    if path.suffix.lower() != ".pdf":
        raise WorkspaceError("Guidelines can be PDF or plain text files.")
    document = pypdfium2.PdfDocument(str(path))
    try:
        out = []
        for number in parse_pages(pages, len(document)):
            textpage = document[number - 1].get_textpage()
            out.append({"page": number, "text": textpage.get_text_range().strip()})
            textpage.close()
        return out
    finally:
        document.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["list", "text"])
    parser.add_argument("name", nargs="?")
    parser.add_argument("--pages")
    args = parser.parse_args()
    try:
        slug = current_project()
        if args.command == "list":
            files = sorted(p.name for p in folder(slug).glob("*") if p.is_file()) if folder(slug).exists() else []
            print_json({"guidelines": files})
        else:
            if not args.name:
                raise WorkspaceError("Say which guideline file to read.")
            pages = read_text(slug, args.name, args.pages)
            if pages and not any(p["text"] for p in pages):
                raise WorkspaceError("This PDF has no text layer (it is a scan). Render its pages as images and read them instead.")
            print_json({"file": args.name, "pages": pages})
    except (WorkspaceError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
