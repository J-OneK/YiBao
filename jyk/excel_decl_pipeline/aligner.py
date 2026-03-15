"""Field matching, coordinate correction and aggregation."""

from __future__ import annotations

import unicodedata
from collections import OrderedDict
from typing import Dict, List, Optional, Tuple

from .models import CellBox, ChunkExtraction, RecognizedField


def _safe_float(value: str) -> Optional[float]:
    try:
        return float(value)
    except Exception:
        return None


def normalize_text(value: str) -> str:
    text = "" if value is None else str(value)
    text = unicodedata.normalize("NFKC", text).strip().lower()
    text = "".join(text.split())

    numeric = _safe_float(text.replace(",", ""))
    if numeric is not None:
        text = f"{numeric:.10f}".rstrip("0").rstrip(".")
    return text


def _normalize_to_real(coord_999: int, size: int) -> int:
    return int(max(0, min(999, coord_999)) * size / 999.0)


def _model_bbox_to_chunk_bbox(field: RecognizedField, chunk_width: int, chunk_height: int) -> Dict[str, int]:
    x1, y1, x2, y2 = field.pixel
    rx1 = _normalize_to_real(x1, chunk_width)
    ry1 = _normalize_to_real(y1, chunk_height)
    rx2 = _normalize_to_real(x2, chunk_width)
    ry2 = _normalize_to_real(y2, chunk_height)
    return {
        "x": min(rx1, rx2),
        "y": min(ry1, ry2),
        "w": max(1, abs(rx2 - rx1)),
        "h": max(1, abs(ry2 - ry1)),
    }


def _bbox_center(box: Dict[str, int]) -> Tuple[float, float]:
    return box["x"] + box["w"] / 2.0, box["y"] + box["h"] / 2.0


def _cell_center(box: CellBox) -> Tuple[float, float]:
    return box.x + box.width / 2.0, box.y + box.height / 2.0


def _match_candidates(value: str, cell_boxes: List[CellBox], model_box: Dict[str, int]) -> Tuple[Optional[CellBox], str]:
    if not value:
        return None, "model_only"

    raw = value.strip()
    norm = normalize_text(raw)

    exact: List[CellBox] = []
    normalized: List[CellBox] = []
    weak: List[CellBox] = []

    for cell_box in cell_boxes:
        cell_text = (cell_box.text or "").strip()
        if not cell_text:
            continue
        if cell_text == raw:
            exact.append(cell_box)
            continue

        cell_norm = normalize_text(cell_text)
        if cell_norm == norm and cell_norm:
            normalized.append(cell_box)
            continue
        if norm and (norm in cell_norm or cell_norm in norm):
            weak.append(cell_box)

    candidates: List[CellBox] = []
    level = "model_only"
    if exact:
        candidates = exact
        level = "exact"
    elif normalized:
        candidates = normalized
        level = "normalized"
    elif weak:
        candidates = weak
        level = "weak"

    if not candidates:
        return None, level

    mx, my = _bbox_center(model_box)
    chosen = min(
        candidates,
        key=lambda box: (abs(_cell_center(box)[0] - mx) + abs(_cell_center(box)[1] - my), box.row, box.col),
    )
    return chosen, level


def _locate_index_by_offset(center_px: float, sizes: List[int], base_index: int) -> int:
    running = 0
    for idx, size in enumerate(sizes):
        running += size
        if center_px <= running:
            return base_index + idx
    return base_index + max(0, len(sizes) - 1)


def _resolve_row_col(
    matched_cell: Optional[CellBox],
    model_box: Dict[str, int],
    chunk,
    model_row_index: Optional[int],
) -> Tuple[int, int]:
    if matched_cell:
        return matched_cell.row, matched_cell.col

    cy = model_box["y"] + model_box["h"] / 2.0
    cx = model_box["x"] + model_box["w"] / 2.0
    row_idx = _locate_index_by_offset(cy, chunk.row_heights_px, chunk.row_range[0])
    col_idx = _locate_index_by_offset(cx, chunk.col_widths_px, chunk.col_range[0])
    if model_row_index is not None:
        row_idx = max(row_idx, chunk.row_range[0] + model_row_index)
    return row_idx, col_idx


def align_and_correct(extractions: List[ChunkExtraction], att_type_code: int) -> Dict:
    head_items: List[Dict] = []
    list_items: List[Dict] = []

    for extraction in extractions:
        chunk = extraction.chunk

        def _process_field(field: RecognizedField):
            model_box = _model_bbox_to_chunk_bbox(field, chunk.width, chunk.height)
            matched_cell, match_level = _match_candidates(field.value, chunk.cell_boxes, model_box)
            coord_corrected = matched_cell is not None
            final_value = matched_cell.text if matched_cell else field.value

            if matched_cell:
                final_box = {
                    "x": matched_cell.x,
                    "y": matched_cell.y,
                    "w": matched_cell.width,
                    "h": matched_cell.height,
                }
            else:
                final_box = model_box

            row_anchor, col_anchor = _resolve_row_col(
                matched_cell=matched_cell,
                model_box=model_box,
                chunk=chunk,
                model_row_index=field.model_row_index,
            )

            return {
                "keyDesc": field.key_desc,
                "key": field.key,
                "value": final_value,
                "area": field.area,
                "sheetIndex": chunk.sheet_index,
                "sheetName": chunk.sheet_name,
                "rowAnchor": row_anchor,
                "colAnchor": col_anchor,
                "source": {
                    "value": final_value,
                    "axisX": int(final_box["x"]),
                    "axisY": int(final_box["y"]),
                    "width": int(final_box["w"]),
                    "height": int(final_box["h"]),
                    "imageId": int(chunk.image_id),
                    "attTypeCode": int(att_type_code),
                    "sheetName": chunk.sheet_name,
                    "sheetIndex": chunk.sheet_index,
                    "row": row_anchor,
                    "col": col_anchor,
                    "matchLevel": match_level if coord_corrected else "model_only",
                    "coordCorrected": coord_corrected,
                },
            }

        for field in extraction.pre_dec_head:
            item = _process_field(field)
            head_items.append(item)

        for row_fields in extraction.pre_dec_list:
            for field in row_fields:
                item = _process_field(field)
                list_items.append(item)

    return {
        "preDecHead": _aggregate_head(head_items),
        "preDecList": _aggregate_list(list_items),
    }


def _aggregate_head(items: List[Dict]) -> List[Dict]:
    grouped: "OrderedDict[str, Dict]" = OrderedDict()
    for item in items:
        key = item["key"] or item["keyDesc"]
        if key not in grouped:
            grouped[key] = {
                "keyDesc": item["keyDesc"],
                "key": item["key"],
                "value": item["value"],
                "sourceList": [],
            }
        grouped[key]["sourceList"].append(item["source"])
    return list(grouped.values())


def _nearest_anchor(entry: Dict, anchors: List[Tuple[int, int, int]]) -> Tuple[int, int, int]:
    if not anchors:
        return entry["sheetIndex"], entry["rowAnchor"], entry["colAnchor"]
    same_sheet = [a for a in anchors if a[0] == entry["sheetIndex"]]
    pool = same_sheet or anchors
    row = entry["rowAnchor"]
    col = entry["colAnchor"]
    return min(pool, key=lambda a: (abs(a[1] - row), abs(a[2] - col), a[0], a[1], a[2]))


def _aggregate_list(items: List[Dict]) -> List[List[Dict]]:
    if not items:
        return []

    code_anchors = sorted(
        {
            (item["sheetIndex"], item["rowAnchor"], item["colAnchor"])
            for item in items
            if item["key"] == "codeTs"
        }
    )

    if code_anchors:
        product_anchors = code_anchors
    else:
        product_anchors = sorted({(item["sheetIndex"], item["rowAnchor"], item["colAnchor"]) for item in items})

    anchor_to_product = {anchor: idx for idx, anchor in enumerate(product_anchors)}
    product_fields: List["OrderedDict[str, Dict]"] = [OrderedDict() for _ in product_anchors]

    for item in items:
        anchor = (item["sheetIndex"], item["rowAnchor"], item["colAnchor"])
        if anchor not in anchor_to_product:
            anchor = _nearest_anchor(item, product_anchors)
        p_idx = anchor_to_product[anchor]

        key = item["key"] or item["keyDesc"]
        if key not in product_fields[p_idx]:
            product_fields[p_idx][key] = {
                "keyDesc": item["keyDesc"],
                "key": item["key"],
                "value": item["value"],
                "sourceList": [],
            }
        product_fields[p_idx][key]["sourceList"].append(item["source"])

    return [list(product.values()) for product in product_fields]

