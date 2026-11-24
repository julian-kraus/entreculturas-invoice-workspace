"""Draw the evidence marks on the invoice pages and save a marked PDF.

Usage:
  ./.tools/uv run tools/marks.py <invoice>
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageDraw

import common
from checks import final_fields
from common import WorkspaceError, current_project, load_json, print_json, project_dir, rel, result_path, work_dir
from grid import font, to_pixels
from pages import render

COLORS = {"passed": (30, 125, 80), "failed": (190, 50, 40), "unclear": (200, 130, 20),
          "not_applicable": (82, 98, 109), "field": (40, 80, 170)}


def marks_for(result: dict) -> list[dict]:
    """One numbered mark per finding with evidence, then per located field without a finding."""
    items, used = [], set()
    for outcome in result.get("rule_results", []):
        evidence = outcome.get("evidence")
        kind = outcome["outcome"]
        # An explicit reviewer decision can keep the evidence for an exempt finding.
        # Existing automatic exemptions have no numbered finding in their saved PDFs.
        has_finding_mark = kind in COLORS and (kind != "not_applicable" or outcome.get("overridden"))
        if evidence and evidence.get("box") and has_finding_mark:
            items.append({"label": outcome["name"], "rule_id": outcome["rule_id"], "page": evidence["page"], "box": evidence["box"],
                          "kind": outcome["outcome"]})
            used.add((evidence["page"], tuple(evidence["box"])))
    for name, field in final_fields(result).items():
        if field.get("box") and (field.get("page"), tuple(field["box"])) not in used:
            items.append({"label": name, "page": field["page"], "box": field["box"],
                          "kind": "unclear" if field.get("status") == "uncertain" else "field"})
    for number, item in enumerate(items, start=1):
        item["number"] = number
    return items


def summary_pages(result: dict, items: list[dict]) -> list[Image.Image]:
    """Create readable pages explaining the findings and numbered marks."""
    pages = []
    width, height, margin = 1240, 1754, 80
    body_font, title_font = font(25), font(38)
    image = None
    canvas = None
    y = 0

    def new_page():
        nonlocal image, canvas, y
        image = Image.new("RGB", (width, height), "white")
        canvas = ImageDraw.Draw(image)
        canvas.text((margin, margin), "Invoice findings", fill="black", font=title_font)
        pages.append(image)
        y = margin + 65

    def write(text):
        nonlocal y
        for paragraph in str(text).split("\n"):
            words = paragraph.split()
            lines, line = [], ""
            for word in words:
                candidate = f"{line} {word}".strip()
                if line and canvas.textlength(candidate, font=body_font) > width - margin * 2:
                    lines.append(line)
                    line = word
                else:
                    line = candidate
            lines.append(line)
            for line in lines:
                if y > height - margin - 36:
                    new_page()
                canvas.text((margin, y), line, fill="black", font=body_font)
                y += 34
        y += 12

    new_page()
    write(f"Document: {result.get('display_file') or result.get('file') or result.get('invoice', '')}")
    review = result.get("review") or {}
    write(f"Review: {review.get('status', 'awaiting confirmation')} · Result: {result.get('status', '')}")
    findings = result.get("rule_results") or []
    if not findings:
        write("No confirmed rules apply to this document.")
    for finding in findings:
        mark = next((m for m in items if m.get("rule_id") == finding.get("rule_id")), None)
        location = f" · Page {mark['page']}, mark {mark['number']}" if mark else ""
        write(f"{finding.get('name', '')} · {finding.get('outcome', '').replace('_', ' ')}{location}")
        if finding.get("message"):
            write(finding["message"])
    return pages


def draw(slug: str, invoice_id: str, *, result: dict | None = None,
         out_dir: Path | None = None, save_pages: bool = True) -> dict:
    if result is None:
        result = load_json(result_path(slug, invoice_id))
    if not result:
        raise WorkspaceError(f"There is no result for '{invoice_id}' yet.")
    page_files = [common.ROOT / page["path"] for page in render(slug, invoice_id, result.get("source_digest"))]
    results_dir = project_dir(slug) / "results"
    if out_dir is None:
        out_dir = work_dir(slug, invoice_id) / "redrawn"
    out_dir.mkdir(parents=True, exist_ok=True)
    items = marks_for(result)
    if any(item["page"] < 1 or item["page"] > len(page_files) for item in items):
        raise WorkspaceError("An evidence box points to a page outside this document. Check its page number.")
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
        if save_pages:
            path = out_dir / f"{invoice_id}-page-{number}.png"
            image.save(path)
            outputs.append(rel(path))
        marked_pages.append(image)
    pdf_path = out_dir / f"{invoice_id}-marked.pdf"
    if not marked_pages:
        raise WorkspaceError("The invoice has no readable pages.")
    all_pages = summary_pages(result, items) + marked_pages
    all_pages[0].save(pdf_path, save_all=True, append_images=all_pages[1:], resolution=150)
    return {"invoice": invoice_id, "marks": items, "pages": outputs, "pdf": rel(pdf_path)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("invoice")
    args = parser.parse_args()
    try:
        print_json(draw(current_project(), args.invoice))
    except WorkspaceError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
