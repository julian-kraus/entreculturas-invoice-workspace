"""Draw the evidence marks on the invoice pages and save a marked PDF.

Usage:
  ./.tools/uv run tools/marks.py <invoice> [--set evaluation]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageDraw

from checks import final_fields
from common import WorkspaceError, current_project, load_json, print_json, rel, result_path, set_dirs, work_dir
from grid import font, to_pixels
from pages import render

COLORS = {"passed": (30, 125, 80), "failed": (190, 50, 40), "unclear": (200, 130, 20), "field": (40, 80, 170)}


def marks_for(result: dict) -> list[dict]:
    """One numbered mark per finding with evidence, then per located field without a finding."""
    items, used = [], set()
    for outcome in result.get("rule_results", []):
        evidence = outcome.get("evidence")
        if evidence and evidence.get("box") and outcome["outcome"] in COLORS:
            items.append({"label": outcome["name"], "page": evidence["page"], "box": evidence["box"],
                          "kind": outcome["outcome"]})
            used.add((evidence["page"], tuple(evidence["box"])))
    for name, field in final_fields(result).items():
        if field.get("box") and (field.get("page"), tuple(field["box"])) not in used:
            items.append({"label": name, "page": field["page"], "box": field["box"],
                          "kind": "unclear" if field.get("status") == "uncertain" else "field"})
    for number, item in enumerate(items, start=1):
        item["number"] = number
    return items


def draw(slug: str, invoice_id: str, which: str) -> dict:
    result = load_json(result_path(slug, invoice_id, which))
    if not result:
        raise WorkspaceError(f"There is no result for '{invoice_id}' yet.")
    pages_dir = work_dir(slug, invoice_id, which)
    if not list(pages_dir.glob("page-*.png")):
        render(slug, invoice_id, which)
    _, results_dir = set_dirs(slug, which)
    out_dir = results_dir / "marked"
    out_dir.mkdir(parents=True, exist_ok=True)
    items = marks_for(result)
    page_files = sorted(pages_dir.glob("page-[0-9]*.png"), key=lambda p: int(p.stem.split("-")[1]))
    page_files = [p for p in page_files if p.stem.count("-") == 1]
    marked_pages, outputs = [], []
    for page_file in page_files:
        number = int(page_file.stem.split("-")[1])
        image = Image.open(page_file).convert("RGB")
        canvas = ImageDraw.Draw(image)
        label_font = font(max(18, image.width // 60))
        for item in (i for i in items if i["page"] == number):
            color = COLORS[item["kind"]]
            left, top, right, bottom = to_pixels(item["box"], image.width, image.height)
            canvas.rectangle([left, top, right, bottom], outline=color, width=5)
            tag = str(item["number"])
            tw = canvas.textlength(tag, font=label_font) + 14
            th = label_font.size + 10 if hasattr(label_font, "size") else 26
            tx, ty = max(0, right - tw), max(0, top - th)
            canvas.rectangle([tx, ty, tx + tw, ty + th], fill=color)
            canvas.text((tx + 7, ty + 4), tag, fill=(255, 255, 255), font=label_font)
        path = out_dir / f"{invoice_id}-page-{number}.png"
        image.save(path)
        outputs.append(rel(path))
        marked_pages.append(image)
    pdf_path = out_dir / f"{invoice_id}-marked.pdf"
    if marked_pages:
        marked_pages[0].save(pdf_path, save_all=True, append_images=marked_pages[1:], resolution=150)
    return {"invoice": invoice_id, "marks": items, "pages": outputs, "pdf": rel(pdf_path)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("invoice")
    parser.add_argument("--set", dest="which", default="invoices", choices=["invoices", "evaluation"])
    args = parser.parse_args()
    try:
        print_json(draw(current_project(), args.invoice, args.which))
    except WorkspaceError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
