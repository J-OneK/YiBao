"""Data models for PDF declaration pipeline test."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class PdfWordBox:
    page_index: int
    text: str
    x: int
    y: int
    width: int
    height: int
    block_no: int
    line_no: int
    word_no: int


@dataclass
class PdfPageModel:
    page_index: int
    image_id: int
    image_path: str
    image_data_url: str
    image_width: int
    image_height: int
    pdf_rect: Tuple[float, float, float, float]
    scale_x: float
    scale_y: float
    word_boxes: List[PdfWordBox] = field(default_factory=list)


@dataclass
class RecognizedField:
    key_desc: str
    key: str
    value: str
    pixel: List[int]  # normalized [0-999]
    area: str  # head or list
    source_image_id: int
    page_index: int
    model_row_index: Optional[int] = None


@dataclass
class PageExtraction:
    page: PdfPageModel
    pre_dec_head: List[RecognizedField] = field(default_factory=list)
    pre_dec_list: List[List[RecognizedField]] = field(default_factory=list)


@dataclass
class AggregatedSource:
    value: str
    axisX: int
    axisY: int
    width: int
    height: int
    imageId: int
    attTypeCode: int
    pdfPage: int
    matchLevel: str
    coordCorrected: bool
    sourceType: str
    lineAnchor: int


@dataclass
class AggregatedField:
    keyDesc: str
    key: str
    value: str
    pageIndex: int
    lineAnchor: int
    source: Dict

