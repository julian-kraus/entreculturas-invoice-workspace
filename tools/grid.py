"""Locate values on a page with a labelled grid, then confirm them on close-up crops.

The page is divided into 12 columns (A-L) and 16 rows (1-16). A range such as "J8:K9"
names a block of cells. Inside a range, a finer 4 x 4 grid (columns a-d, rows 1-4)
narrows it down, e.g. "b2:c3".

Usage:
  python tools/grid.py grid <page.png>
      Writes <page>-grid.png with labelled cells. Look at it and note the cells for each value.
  python tools/grid.py sheet <page.png> <spec.json>
      spec: {"total_amount": "J8:K8", "stamp": "E6:I8"}
      Writes <page>-sheet.png: each range enlarged with the finer a-d / 1-4 grid.
  python tools/grid.py finalize <page.png> <spec.json>
      spec: {"total_amount": {"cells": "J8:K8", "sub": "a2:d3"}, "stamp": {"cells": "E6:I8"}}
      Prints the final boxes (fractions of the page) and writes <page>-check.png showing
      each box in red with some surrounding context. Look at it to confirm every value
      sits fully inside its red frame.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

COLS = "ABCDEFGHIJKL"
ROWS = 16
SUB_COLS = "abcd"
SUB_ROWS = 4
SHEET_WIDTH = 760

GRID_COLOR = (0, 150, 60)
FRAME_COLOR = (220, 30, 30)


class GridError(ValueError):
    pass


def font(size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _parse_range(text: str, cols: str, rows: int) -> tuple[int, int, int, int]:
    parts = [p.strip() for p in str(text).split(":")]
    if len(parts) == 1:
        parts = parts * 2
    if len(parts) != 2:
        raise GridError(f"'{text}' is not a range like J8:K9.")
    cells = []
    for part in parts:
        match = re.fullmatch(r"([A-Za-z])(\d{1,2})", part)
        if not match:
            raise GridError(f"'{part}' is not a cell like J8.")
        letter, number = match.group(1), int(match.group(2))
        letter = letter.upper() if cols.isupper() else letter.lower()
        if letter not in cols or not 1 <= number <= rows:
            raise GridError(f"'{part}' is outside the grid.")
        cells.append((cols.index(letter), number - 1))
    (c0, r0), (c1, r1) = cells
    return min(c0, c1), min(r0, r1), max(c0, c1), max(r0, r1)


def range_box(cells: str) -> list[float]:
    c0, r0, c1, r1 = _parse_range(cells, COLS, ROWS)
    return [c0 / len(COLS), r0 / ROWS, (c1 + 1) / len(COLS), (r1 + 1) / ROWS]


def refine_box(cells: str, sub: str | None) -> list[float]:
    x0, y0, x1, y1 = range_box(cells)
    if not sub:
        return [round(v, 4) for v in (x0, y0, x1, y1)]
    s0, t0, s1, t1 = _parse_range(sub, SUB_COLS, SUB_ROWS)
    w, h = x1 - x0, y1 - y0
    box = [x0 + w * s0 / len(SUB_COLS), y0 + h * t0 / SUB_ROWS,
           x0 + w * (s1 + 1) / len(SUB_COLS), y0 + h * (t1 + 1) / SUB_ROWS]
    return [round(v, 4) for v in box]


def to_pixels(box: list[float], width: int, height: int) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = box
    return int(x0 * width), int(y0 * height), int(round(x1 * width)), int(round(y1 * height))


def draw_grid(page: Image.Image) -> Image.Image:
    image = page.convert("RGB").copy()
    draw = ImageDraw.Draw(image)
    w, h = image.size
    label_font = font(max(14, w // 70))
    for c in range(len(COLS) + 1):
        x = round(c * w / len(COLS))
        draw.line([(x, 0), (x, h)], fill=GRID_COLOR, width=2)
    for r in range(ROWS + 1):
        y = round(r * h / ROWS)
        draw.line([(0, y), (w, y)], fill=GRID_COLOR, width=2)
    for c, letter in enumerate(COLS):
        for r in range(ROWS):
            x, y = c * w / len(COLS) + 4, r * h / ROWS + 2
            draw.text((x, y), f"{letter}{r + 1}", fill=GRID_COLOR, font=label_font,
                      stroke_width=2, stroke_fill=(255, 255, 255))
    return image


def _titled(image: Image.Image, title: str) -> Image.Image:
    scale = SHEET_WIDTH / image.width
    image = image.resize((SHEET_WIDTH, max(1, int(image.height * scale))))
    bar = 34
    framed = Image.new("RGB", (SHEET_WIDTH, image.height + bar), (255, 255, 255))
    ImageDraw.Draw(framed).text((8, 6), title, fill=(20, 20, 20), font=font(20))
    framed.paste(image, (0, bar))
    return framed


def _stack(parts: list[Image.Image]) -> Image.Image:
    gap = 16
    height = sum(p.height for p in parts) + gap * (len(parts) - 1)
    sheet = Image.new("RGB", (SHEET_WIDTH, max(height, 1)), (235, 235, 235))
    y = 0
    for part in parts:
        sheet.paste(part, (0, y))
        y += part.height + gap
    return sheet


def make_sheet(page: Image.Image, spec: dict) -> Image.Image:
    w, h = page.size
    parts = []
    for name, cells in spec.items():
        if isinstance(cells, dict):
            cells = cells.get("cells", "")
        left, top, right, bottom = to_pixels(range_box(cells), w, h)
        crop = page.crop((left, top, right, bottom)).convert("RGB")
        draw = ImageDraw.Draw(crop)
        cw, ch = crop.size
        sub_font = font(max(12, min(cw, ch) // 9))
        for i in range(len(SUB_COLS) + 1):
            x = round(i * cw / len(SUB_COLS))
            draw.line([(x, 0), (x, ch)], fill=GRID_COLOR, width=1)
        for j in range(SUB_ROWS + 1):
            y = round(j * ch / SUB_ROWS)
            draw.line([(0, y), (cw, y)], fill=GRID_COLOR, width=1)
        for i, letter in enumerate(SUB_COLS):
            for j in range(SUB_ROWS):
                draw.text((i * cw / len(SUB_COLS) + 2, j * ch / SUB_ROWS + 1), f"{letter}{j + 1}",
                          fill=GRID_COLOR, font=sub_font, stroke_width=1, stroke_fill=(255, 255, 255))
        parts.append(_titled(crop, f"{name}  ({cells})"))
    return _stack(parts)


def make_check(page: Image.Image, boxes: dict[str, list[float]]) -> Image.Image:
    w, h = page.size
    parts = []
    for name, box in boxes.items():
        left, top, right, bottom = to_pixels(box, w, h)
        pad_x = max(int((right - left) * 0.4), w // 40)
        pad_y = max(int((bottom - top) * 0.4), h // 60)
        area = (max(0, left - pad_x), max(0, top - pad_y), min(w, right + pad_x), min(h, bottom + pad_y))
        crop = page.crop(area).convert("RGB")
        ImageDraw.Draw(crop).rectangle(
            [left - area[0], top - area[1], right - area[0] - 1, bottom - area[1] - 1],
            outline=FRAME_COLOR, width=3)
        parts.append(_titled(crop, name))
    return _stack(parts)


def _out_path(page_path: Path, suffix: str) -> Path:
    return page_path.with_name(f"{page_path.stem}-{suffix}.png")


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[0] not in {"grid", "sheet", "finalize"}:
        print(__doc__, file=sys.stderr)
        return 2
    command, page_path = argv[0], Path(argv[1])
    try:
        page = Image.open(page_path).convert("RGB")
        if command == "grid":
            out = _out_path(page_path, "grid")
            draw_grid(page).save(out)
            print(json.dumps({"grid_image": str(out), "columns": COLS, "rows": ROWS}))
            return 0
        if len(argv) < 3:
            raise GridError("Give the spec file as the third argument.")
        spec = json.loads(Path(argv[2]).read_text(encoding="utf-8"))
        if not isinstance(spec, dict) or not spec:
            raise GridError("The spec must be a JSON object with at least one entry.")
        if command == "sheet":
            out = _out_path(page_path, "sheet")
            make_sheet(page, spec).save(out)
            print(json.dumps({"sheet_image": str(out)}))
            return 0
        boxes = {}
        for name, entry in spec.items():
            entry = {"cells": entry} if isinstance(entry, str) else entry
            boxes[name] = refine_box(entry["cells"], entry.get("sub"))
        out = _out_path(page_path, "check")
        make_check(page, boxes).save(out)
        print(json.dumps({"boxes": boxes, "check_image": str(out)}))
        return 0
    except (GridError, KeyError, json.JSONDecodeError, OSError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
