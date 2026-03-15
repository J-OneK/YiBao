"""Render trimmed sheet models to images with AutoFit sizing."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Dict, List, Tuple

from PIL import Image, ImageDraw, ImageFont

from .models import CellBox, RenderedSheet, SheetModel

H_PADDING = 6
V_PADDING = 4
MIN_ROW_PX = 16
MAX_ROW_PX = 300
MIN_COL_PX = 30
MAX_COL_PX = 420
FONT_SIZE = 13


def _load_font(size: int = FONT_SIZE) -> ImageFont.ImageFont:
    repo_root = Path(__file__).resolve().parents[2]
    candidates = [
        repo_root / "wzh" / "excel" / "fonts" / "wqy-zenhei.ttc",
        repo_root / "wzh" / "excel" / "fonts" / "NotoSansCJK-Regular.ttc",
    ]
    for path in candidates:
        if path.exists():
            try:
                return ImageFont.truetype(str(path), size=size)
            except Exception:
                continue
    return ImageFont.load_default()


def _measure(text: str, font: ImageFont.ImageFont) -> Tuple[int, int]:
    if not text:
        return 0, font.size
    box = font.getbbox(text)
    return box[2] - box[0], box[3] - box[1]


def _wrap_line(text: str, font: ImageFont.ImageFont, max_width: int) -> List[str]:
    if not text:
        return [""]
    if max_width <= 1:
        return [text]

    lines: List[str] = []
    buffer = ""
    for char in text:
        candidate = f"{buffer}{char}"
        w, _ = _measure(candidate, font)
        if w <= max_width or not buffer:
            buffer = candidate
            continue
        lines.append(buffer)
        buffer = char
    if buffer:
        lines.append(buffer)
    return lines


def _wrap_text(text: str, font: ImageFont.ImageFont, max_width: int) -> List[str]:
    lines: List[str] = []
    for part in (text or "").splitlines() or [""]:
        lines.extend(_wrap_line(part, font, max_width))
    return lines or [""]


def _autosize(sheet: SheetModel) -> None:
    font = _load_font()
    col_widths = [max(MIN_COL_PX, min(MAX_COL_PX, w)) for w in sheet.col_widths_px]
    row_heights = [max(MIN_ROW_PX, min(MAX_ROW_PX, h)) for h in sheet.row_heights_px]

    # Pass 1: expand columns to reduce clipping.
    for cell in sheet.cells.values():
        if cell.is_merged_child or not (cell.value or "").strip():
            continue
        usable_lines = (cell.value or "").splitlines() or [""]
        max_line_w = max(_measure(line, font)[0] for line in usable_lines)
        needed_w = max_line_w + H_PADDING * 2

        span = max(cell.merge_span_col, 1)
        col_start = cell.col
        col_end = min(cell.col + span, len(col_widths))
        current_w = sum(col_widths[col_start:col_end])

        if needed_w <= current_w:
            continue

        delta = needed_w - current_w
        step = int(math.ceil(delta / float(col_end - col_start)))
        for c in range(col_start, col_end):
            col_widths[c] = min(MAX_COL_PX, col_widths[c] + step)

    # Pass 2: expand row heights so wrapped text is fully visible.
    for cell in sheet.cells.values():
        if cell.is_merged_child or not (cell.value or "").strip():
            continue

        row_start = cell.row
        row_end = min(cell.row + max(cell.merge_span_row, 1), len(row_heights))
        col_start = cell.col
        col_end = min(cell.col + max(cell.merge_span_col, 1), len(col_widths))

        cell_w = sum(col_widths[col_start:col_end]) - H_PADDING * 2
        wrapped = _wrap_text(cell.value, font, cell_w)
        _, line_h = _measure("Ag", font)
        needed_h = len(wrapped) * max(line_h + 2, font.size) + V_PADDING * 2
        current_h = sum(row_heights[row_start:row_end])

        if needed_h <= current_h:
            continue

        delta = needed_h - current_h
        step = int(math.ceil(delta / float(row_end - row_start)))
        for r in range(row_start, row_end):
            row_heights[r] = min(MAX_ROW_PX, row_heights[r] + step)

    sheet.col_widths_px = col_widths
    sheet.row_heights_px = row_heights


def render_sheet(sheet: SheetModel, sheet_index: int) -> RenderedSheet:
    _autosize(sheet)
    font = _load_font()

    xs = [0]
    for width in sheet.col_widths_px:
        xs.append(xs[-1] + int(width))
    ys = [0]
    for height in sheet.row_heights_px:
        ys.append(ys[-1] + int(height))

    image = Image.new("RGB", (max(xs[-1], 1), max(ys[-1], 1)), "white")
    draw = ImageDraw.Draw(image)
    cell_boxes: Dict[Tuple[int, int], CellBox] = {}

    for cell in sheet.cells.values():
        if cell.is_merged_child:
            continue
        row = cell.row
        col = cell.col
        row_end = min(row + max(cell.merge_span_row, 1), sheet.n_rows)
        col_end = min(col + max(cell.merge_span_col, 1), sheet.n_cols)

        x0 = xs[col]
        y0 = ys[row]
        x1 = xs[col_end]
        y1 = ys[row_end]
        width = max(1, x1 - x0)
        height = max(1, y1 - y0)

        draw.rectangle((x0, y0, x1 - 1, y1 - 1), outline=(180, 180, 180), width=1)

        text = (cell.value or "").strip()
        if text:
            wrapped = _wrap_text(text, font, max(1, width - H_PADDING * 2))
            _, line_h = _measure("Ag", font)
            line_h = max(line_h + 2, font.size)
            ty = y0 + V_PADDING
            for line in wrapped:
                if ty + line_h > y1:
                    break
                draw.text((x0 + H_PADDING, ty), line, fill=(0, 0, 0), font=font)
                ty += line_h

            cell_boxes[(row, col)] = CellBox(
                sheet_name=sheet.name,
                sheet_index=sheet_index,
                row=row,
                col=col,
                row_span=max(cell.merge_span_row, 1),
                col_span=max(cell.merge_span_col, 1),
                text=text,
                x=x0,
                y=y0,
                width=width,
                height=height,
            )

    return RenderedSheet(
        sheet_name=sheet.name,
        sheet_index=sheet_index,
        image=image,
        row_heights_px=sheet.row_heights_px,
        col_widths_px=sheet.col_widths_px,
        cell_boxes=cell_boxes,
    )

