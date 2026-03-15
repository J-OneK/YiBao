"""PDF page rendering and words-level source coordinate extraction."""

from __future__ import annotations

import base64
import io
from pathlib import Path
from typing import List, Tuple

from .models import PdfPageModel, PdfWordBox


def _to_data_url(image_bytes: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(image_bytes).decode("utf-8")


def _compute_render_zoom(base_zoom: float, width: int, height: int, max_side: int) -> float:
    if width <= max_side and height <= max_side:
        return base_zoom
    shrink_ratio = min(max_side / float(width), max_side / float(height))
    return base_zoom * shrink_ratio


def _ensure_fitz():
    try:
        import fitz  # type: ignore
    except Exception as exc:  # pragma: no cover - environment specific
        raise ImportError(
            "PyMuPDF is required for pdf_decl_pipeline_test. Install with: pip install pymupdf"
        ) from exc
    return fitz


def load_pdf_pages(
    pdf_path: str,
    output_dir: Path,
    max_side: int = 4096,
    dpi: int = 216,
) -> List[PdfPageModel]:
    fitz = _ensure_fitz()
    doc = fitz.open(pdf_path)
    output_dir.mkdir(parents=True, exist_ok=True)

    pages: List[PdfPageModel] = []
    base_zoom = dpi / 72.0
    image_id = 1

    try:
        for page_index in range(doc.page_count):
            page = doc[page_index]
            rect = page.rect
            rect_tuple: Tuple[float, float, float, float] = (rect.x0, rect.y0, rect.x1, rect.y1)

            base_matrix = fitz.Matrix(base_zoom, base_zoom)
            base_pix = page.get_pixmap(matrix=base_matrix, alpha=False)
            zoom = _compute_render_zoom(base_zoom, base_pix.width, base_pix.height, max_side=max_side)
            matrix = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=matrix, alpha=False)

            image_name = f"page_{page_index + 1:03d}.png"
            image_path = output_dir / image_name
            image_bytes = pix.tobytes("png")
            with open(image_path, "wb") as f:
                f.write(image_bytes)

            scale_x = pix.width / float(rect.width) if rect.width else 1.0
            scale_y = pix.height / float(rect.height) if rect.height else 1.0

            words_raw = page.get_text("words")
            word_boxes: List[PdfWordBox] = []
            for raw in words_raw:
                if len(raw) < 8:
                    continue
                x0, y0, x1, y1, text, block_no, line_no, word_no = raw[:8]
                text = "" if text is None else str(text)
                if not text.strip():
                    continue
                ix0 = int(round(float(x0) * scale_x))
                iy0 = int(round(float(y0) * scale_y))
                ix1 = int(round(float(x1) * scale_x))
                iy1 = int(round(float(y1) * scale_y))
                word_boxes.append(
                    PdfWordBox(
                        page_index=page_index,
                        text=text,
                        x=min(ix0, ix1),
                        y=min(iy0, iy1),
                        width=max(1, abs(ix1 - ix0)),
                        height=max(1, abs(iy1 - iy0)),
                        block_no=int(block_no),
                        line_no=int(line_no),
                        word_no=int(word_no),
                    )
                )
            print(word_boxes)
            pages.append(
                PdfPageModel(
                    page_index=page_index,
                    image_id=image_id,
                    image_path=str(image_path),
                    image_data_url=_to_data_url(image_bytes),
                    image_width=pix.width,
                    image_height=pix.height,
                    pdf_rect=rect_tuple,
                    scale_x=scale_x,
                    scale_y=scale_y,
                    word_boxes=word_boxes,
                )
            )
            image_id += 1
    finally:
        doc.close()

    return pages

