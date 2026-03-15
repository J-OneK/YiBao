"""Split rendered sheet images by Excel row/column boundaries."""

from __future__ import annotations

import base64
import io
import re
from pathlib import Path
from typing import List, Sequence, Tuple

from .models import CellBox, Chunk, RenderedSheet


def _sanitize_filename(name: str) -> str:
    return re.sub(r'[\\/*?:"<>|]', "_", name)


def _build_segments(sizes: Sequence[int], max_side: int) -> List[Tuple[int, int, int, int]]:
    """
    Returns (start_idx, end_idx, offset_px, total_px), inclusive indices.
    """
    if not sizes:
        return []

    segments: List[Tuple[int, int, int, int]] = []
    start_idx = 0
    start_offset = 0
    current_total = 0
    offset = 0

    for idx, size in enumerate(sizes):
        size = int(size)
        if current_total + size > max_side and idx > start_idx:
            segments.append((start_idx, idx - 1, start_offset, current_total))
            start_idx = idx
            start_offset = offset
            current_total = 0

        current_total += size
        offset += size

    segments.append((start_idx, len(sizes) - 1, start_offset, current_total))
    return segments


def _image_to_data_url(image) -> str:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    data = base64.b64encode(buffer.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{data}"


def split_rendered_sheet(
    rendered: RenderedSheet,
    max_side: int,
    image_id_start: int,
    chunk_output_dir: Path,
) -> List[Chunk]:
    chunk_output_dir.mkdir(parents=True, exist_ok=True)
    row_segments = _build_segments(rendered.row_heights_px, max_side)
    col_segments = _build_segments(rendered.col_widths_px, max_side)

    chunks: List[Chunk] = []
    image_id = image_id_start
    sheet_safe = _sanitize_filename(rendered.sheet_name)

    for r_start, r_end, y_off, chunk_h in row_segments:
        for c_start, c_end, x_off, chunk_w in col_segments:
            bbox = (x_off, y_off, x_off + chunk_w, y_off + chunk_h)
            chunk_image = rendered.image.crop(bbox)
            filename = f"{sheet_safe}__r{r_start}-{r_end}__c{c_start}-{c_end}.png"
            image_path = chunk_output_dir / filename
            chunk_image.save(image_path)

            chunk_cell_boxes: List[CellBox] = []
            for cell_box in rendered.cell_boxes.values():
                cell_x1 = cell_box.x
                cell_y1 = cell_box.y
                cell_x2 = cell_box.x + cell_box.width
                cell_y2 = cell_box.y + cell_box.height

                inter_x1 = max(cell_x1, x_off)
                inter_y1 = max(cell_y1, y_off)
                inter_x2 = min(cell_x2, x_off + chunk_w)
                inter_y2 = min(cell_y2, y_off + chunk_h)
                if inter_x2 <= inter_x1 or inter_y2 <= inter_y1:
                    continue

                chunk_cell_boxes.append(
                    CellBox(
                        sheet_name=cell_box.sheet_name,
                        sheet_index=cell_box.sheet_index,
                        row=cell_box.row,
                        col=cell_box.col,
                        row_span=cell_box.row_span,
                        col_span=cell_box.col_span,
                        text=cell_box.text,
                        x=inter_x1 - x_off,
                        y=inter_y1 - y_off,
                        width=inter_x2 - inter_x1,
                        height=inter_y2 - inter_y1,
                    )
                )

            chunk = Chunk(
                chunk_id=f"{sheet_safe}:{r_start}-{r_end}:{c_start}-{c_end}",
                image_id=image_id,
                sheet_name=rendered.sheet_name,
                sheet_index=rendered.sheet_index,
                row_range=(r_start, r_end),
                col_range=(c_start, c_end),
                offset_x=x_off,
                offset_y=y_off,
                width=chunk_w,
                height=chunk_h,
                image=chunk_image,
                image_data_url=_image_to_data_url(chunk_image),
                image_path=str(image_path),
                cell_boxes=chunk_cell_boxes,
                row_heights_px=rendered.row_heights_px[r_start : r_end + 1],
                col_widths_px=rendered.col_widths_px[c_start : c_end + 1],
            )
            chunks.append(chunk)
            image_id += 1
    return chunks

