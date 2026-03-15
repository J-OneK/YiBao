"""Cross-validate model results with PDF words and correct coordinates."""

from __future__ import annotations

import unicodedata
from collections import OrderedDict
from typing import Dict, List, Optional, Tuple

from .models import PageExtraction, PdfWordBox, RecognizedField


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


def _model_bbox_to_page_bbox(field: RecognizedField, image_width: int, image_height: int) -> Dict[str, int]:
    x1, y1, x2, y2 = field.pixel
    rx1 = _normalize_to_real(x1, image_width)
    ry1 = _normalize_to_real(y1, image_height)
    rx2 = _normalize_to_real(x2, image_width)
    ry2 = _normalize_to_real(y2, image_height)
    return {
        "x": min(rx1, rx2),
        "y": min(ry1, ry2),
        "w": max(1, abs(rx2 - rx1)),
        "h": max(1, abs(ry2 - ry1)),
    }


def _bbox_center(box: Dict[str, int]) -> Tuple[float, float]:
    return box["x"] + box["w"] / 2.0, box["y"] + box["h"] / 2.0


def _word_center(word: PdfWordBox) -> Tuple[float, float]:
    return word.x + word.width / 2.0, word.y + word.height / 2.0


def _union_words(words: List[PdfWordBox]) -> Dict[str, int]:
    x1 = min(w.x for w in words)
    y1 = min(w.y for w in words)
    x2 = max(w.x + w.width for w in words)
    y2 = max(w.y + w.height for w in words)
    return {"x": x1, "y": y1, "w": max(1, x2 - x1), "h": max(1, y2 - y1)}


def _match_word_candidates(value: str, words: List[PdfWordBox], model_box: Dict[str, int]):
    if not value:
        return None, "model_only", None

    raw = value.strip()
    norm = normalize_text(raw)
    exact: List[PdfWordBox] = []
    normalized: List[PdfWordBox] = []
    weak: List[PdfWordBox] = []

    for word in words:
        word_text = (word.text or "").strip()
        if not word_text:
            continue
        if word_text == raw:
            exact.append(word)
            continue
        word_norm = normalize_text(word_text)
        if word_norm and word_norm == norm:
            normalized.append(word)
            continue
        if norm and (norm in word_norm or word_norm in norm):
            weak.append(word)

    candidates: List[PdfWordBox] = []
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
        return None, level, None

    mx, my = _bbox_center(model_box)
    pivot = min(candidates, key=lambda w: (abs(_word_center(w)[0] - mx) + abs(_word_center(w)[1] - my), w.y, w.x))

    # Optional union for long phrases that likely span multiple adjacent words.
    union_box = None
    if level == "weak":
        pivot_norm = normalize_text(pivot.text)
        if pivot_norm and len(norm) > len(pivot_norm) * 1.5:
            same_line = [
                w
                for w in candidates
                if w.block_no == pivot.block_no and w.line_no == pivot.line_no and abs(w.y - pivot.y) <= max(4, pivot.height)
            ]
            if len(same_line) > 1:
                union_box = _union_words(sorted(same_line, key=lambda w: (w.x, w.word_no)))
                level = "weak_union"

    return pivot, level, union_box


def _resolve_line_anchor(matched_word: Optional[PdfWordBox], model_box: Dict[str, int], extraction: PageExtraction, field: RecognizedField) -> int:
    if matched_word:
        return int(matched_word.line_no)

    # fallback by vertical nearest line center
    if extraction.page.word_boxes:
        cy = model_box["y"] + model_box["h"] / 2.0
        line_map: Dict[int, List[PdfWordBox]] = {}
        for w in extraction.page.word_boxes:
            line_map.setdefault(w.line_no, []).append(w)
        line_centers = []
        for line_no, ws in line_map.items():
            avg = sum(w.y + w.height / 2.0 for w in ws) / len(ws)
            line_centers.append((line_no, avg))
        best_line = min(line_centers, key=lambda t: abs(t[1] - cy))[0]
        if field.model_row_index is not None:
            return max(int(best_line), field.model_row_index)
        return int(best_line)
    return int(field.model_row_index or 0)


def align_and_correct_pdf(extractions: List[PageExtraction], att_type_code: int) -> Dict:
    head_items: List[Dict] = []
    list_items: List[Dict] = []

    for extraction in extractions:
        page = extraction.page

        def _process_field(field: RecognizedField):
            model_box = _model_bbox_to_page_bbox(field, page.image_width, page.image_height)
            matched_word, match_level, union_box = _match_word_candidates(field.value, page.word_boxes, model_box)
            coord_corrected = matched_word is not None

            if matched_word is not None:
                final_value = matched_word.text
                if union_box:
                    final_box = union_box
                else:
                    final_box = {"x": matched_word.x, "y": matched_word.y, "w": matched_word.width, "h": matched_word.height}
                source_type = "pdf_word"
            else:
                final_value = field.value
                final_box = model_box
                source_type = "model_box"

            line_anchor = _resolve_line_anchor(matched_word, model_box, extraction, field)

            return {
                "keyDesc": field.key_desc,
                "key": field.key,
                "value": final_value,
                "area": field.area,
                "pageIndex": page.page_index,
                "lineAnchor": line_anchor,
                "source": {
                    "value": final_value,
                    "axisX": int(final_box["x"]),
                    "axisY": int(final_box["y"]),
                    "width": int(final_box["w"]),
                    "height": int(final_box["h"]),
                    "imageId": int(page.image_id),
                    "attTypeCode": int(att_type_code),
                    "pdfPage": int(page.page_index),
                    "matchLevel": match_level if coord_corrected else "model_only",
                    "coordCorrected": coord_corrected,
                    "sourceType": source_type,
                    "lineAnchor": int(line_anchor),
                },
            }

        for field in extraction.pre_dec_head:
            head_items.append(_process_field(field))
        for row_fields in extraction.pre_dec_list:
            for field in row_fields:
                list_items.append(_process_field(field))

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


def _nearest_anchor(entry: Dict, anchors: List[Tuple[int, int]]) -> Tuple[int, int]:
    if not anchors:
        return entry["pageIndex"], entry["lineAnchor"]
    same_page = [a for a in anchors if a[0] == entry["pageIndex"]]
    pool = same_page or anchors
    return min(pool, key=lambda a: (abs(a[1] - entry["lineAnchor"]), a[0], a[1]))


def _aggregate_list(items: List[Dict]) -> List[List[Dict]]:
    if not items:
        return []

    code_anchors = sorted({(item["pageIndex"], item["lineAnchor"]) for item in items if item["key"] == "codeTs"})
    if code_anchors:
        product_anchors = code_anchors
    else:
        product_anchors = sorted({(item["pageIndex"], item["lineAnchor"]) for item in items})

    anchor_to_product = {anchor: idx for idx, anchor in enumerate(product_anchors)}
    product_fields: List["OrderedDict[str, Dict]"] = [OrderedDict() for _ in product_anchors]

    for item in items:
        anchor = (item["pageIndex"], item["lineAnchor"])
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

