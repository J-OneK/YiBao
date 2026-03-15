"""Shared data models for the Excel declaration OCR pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from PIL import Image


@dataclass
class CellModel:
    row: int
    col: int
    value: str
    merge_span_row: int = 1
    merge_span_col: int = 1
    is_merged_child: bool = False


@dataclass
class SheetModel:
    name: str
    cells: Dict[Tuple[int, int], CellModel]
    n_rows: int
    n_cols: int
    row_heights_px: List[int]
    col_widths_px: List[int]


@dataclass
class WorkbookModel:
    source_path: str
    sheets: List[SheetModel]


@dataclass
class CellBox:
    sheet_name: str
    sheet_index: int
    row: int
    col: int
    row_span: int
    col_span: int
    text: str
    x: int
    y: int
    width: int
    height: int


@dataclass
class RenderedSheet:
    sheet_name: str
    sheet_index: int
    image: Image.Image
    row_heights_px: List[int]
    col_widths_px: List[int]
    cell_boxes: Dict[Tuple[int, int], CellBox]

    @property
    def width(self) -> int:
        return self.image.width

    @property
    def height(self) -> int:
        return self.image.height


@dataclass
class Chunk:
    chunk_id: str
    image_id: int
    sheet_name: str
    sheet_index: int
    row_range: Tuple[int, int]
    col_range: Tuple[int, int]
    offset_x: int
    offset_y: int
    width: int
    height: int
    image: Image.Image
    image_data_url: str
    image_path: str
    cell_boxes: List[CellBox] = field(default_factory=list)
    row_heights_px: List[int] = field(default_factory=list)
    col_widths_px: List[int] = field(default_factory=list)


@dataclass
class RecognizedField:
    key_desc: str
    key: str
    value: str
    pixel: List[int]
    area: str  # "head" or "list"
    source_image_id: int
    model_row_index: Optional[int] = None


@dataclass
class ChunkExtraction:
    chunk: Chunk
    pre_dec_head: List[RecognizedField] = field(default_factory=list)
    pre_dec_list: List[List[RecognizedField]] = field(default_factory=list)

