"""Build OCR-compatible output JSON with PDF correction metadata."""

from __future__ import annotations

import time
from typing import Dict, List

from jyk.excel_decl_pipeline.field_mapping_loader import get_att_type_name_en

from .models import PdfPageModel


def _transform_source(source: Dict, att_type_code: int) -> Dict:
    value = source.get("value", "")
    return {
        "attType": get_att_type_name_en(att_type_code),
        "imageId": source.get("imageId"),
        "transformValue": None,
        "originalValue": value,
        "normalizedValue": value,
        "processBitMap": "0",
        "axisX": source.get("axisX", 0),
        "sepValue": value,
        "axisY": source.get("axisY", 0),
        "width": source.get("width", 0),
        "attTypeCode": att_type_code,
        "height": source.get("height", 0),
        "pdfPage": source.get("pdfPage"),
        "matchLevel": source.get("matchLevel"),
        "coordCorrected": source.get("coordCorrected", False),
        "sourceType": source.get("sourceType"),
        "lineAnchor": source.get("lineAnchor"),
    }


def _transform_field_item(item: Dict, att_type_code: int) -> Dict:
    source_list = [_transform_source(src, att_type_code) for src in item.get("sourceList", [])]
    value = item.get("value", "")
    source_image = source_list[0]["imageId"] if source_list else None
    return {
        "processBitMap": "0",
        "sourceList": source_list,
        "source_image": source_image,
        "originalValue": value,
        "normalizedValue": value,
        "keyDesc": item.get("keyDesc"),
        "value": value,
        "key": item.get("key"),
    }


def _build_operate_image(pages: List[PdfPageModel], att_type_code: int) -> List[Dict]:
    results: List[Dict] = []
    for page in pages:
        results.append(
            {
                "imageId": page.image_id,
                "imageUrl": page.image_path,
                "imageWidth": page.image_width,
                "imageHeight": page.image_height,
                "attTypeCode": att_type_code,
                "pdfDocPage": page.page_index,
                "pdfRect": list(page.pdf_rect),
                "scaleX": page.scale_x,
                "scaleY": page.scale_y,
            }
        )
    return results


def build_ocr_json(aggregated: Dict, pages: List[PdfPageModel], att_type_code: int) -> Dict:
    pre_dec_head: List[Dict] = []
    pre_dec_container: List[List[Dict]] = []
    for item in aggregated.get("preDecHead", []):
        transformed = _transform_field_item(item, att_type_code)
        if transformed.get("key") == "containerNo":
            pre_dec_container.append([transformed])
        else:
            pre_dec_head.append(transformed)

    pre_dec_list: List[List[Dict]] = []
    for row in aggregated.get("preDecList", []):
        pre_dec_list.append([_transform_field_item(item, att_type_code) for item in row])

    return {
        "head": {
            "resultCode": "0",
            "resultMessage": "识别成功",
            "version": "1.0",
            "timestampStr": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
        },
        "content": {
            "preDecHead": pre_dec_head,
            "preDecList": pre_dec_list,
            "operateImage": _build_operate_image(pages, att_type_code),
            "preDecContainer": pre_dec_container,
        },
    }

