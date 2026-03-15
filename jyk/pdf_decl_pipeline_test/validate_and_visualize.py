"""Validate PDF pipeline output and export visualization images.

Example:
    python jyk/pdf_decl_pipeline_test/validate_and_visualize.py \
      --output_json d:/code/YiBao/jyk/pdf_decl_pipeline_test/output.json \
      --pdf_path d:/code/YiBao/jyk/pdf_decl_pipeline_test/ED.pdf
"""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont


@dataclass
class Issue:
    level: str  # error/warn/info
    image_id: str
    key_desc: str
    message: str


@dataclass
class SourceItem:
    image_id: str
    key_desc: str
    value: str
    axis_x: int
    axis_y: int
    width: int
    height: int
    pdf_page: Optional[int]
    match_level: str
    coord_corrected: bool
    source_type: str

    @property
    def box(self) -> Tuple[int, int, int, int]:
        return (
            self.axis_x,
            self.axis_y,
            self.axis_x + max(1, self.width),
            self.axis_y + max(1, self.height),
        )


def _safe_int(value, default=0) -> int:
    try:
        return int(round(float(value)))
    except Exception:
        return default


def _safe_str(value) -> str:
    return "" if value is None else str(value)


def normalize_text(value: str) -> str:
    text = unicodedata.normalize("NFKC", _safe_str(value)).strip().lower()
    text = "".join(text.split())
    try:
        num = float(text.replace(",", ""))
        text = f"{num:.10f}".rstrip("0").rstrip(".")
    except Exception:
        pass
    return text


def _flatten_operate_image(raw) -> List[Dict]:
    if not isinstance(raw, list):
        return []
    items: List[Dict] = []
    for item in raw:
        if isinstance(item, dict):
            items.append(item)
        elif isinstance(item, list):
            for sub in item:
                if isinstance(sub, dict):
                    items.append(sub)
    return items


def _iter_field_items(content: Dict) -> Iterable[Dict]:
    for item in content.get("preDecHead", []):
        if isinstance(item, dict):
            yield item
    for row in content.get("preDecList", []):
        if isinstance(row, list):
            for item in row:
                if isinstance(item, dict):
                    yield item
    for row in content.get("preDecContainer", []):
        if isinstance(row, list):
            for item in row:
                if isinstance(item, dict):
                    yield item


def _build_image_map(content: Dict, base_dir: Path) -> Tuple[Dict[str, Path], Dict[str, Dict]]:
    image_path_map: Dict[str, Path] = {}
    image_meta_map: Dict[str, Dict] = {}
    for op in _flatten_operate_image(content.get("operateImage", [])):
        image_id = _safe_str(op.get("imageId")).strip()
        if not image_id:
            continue
        image_url = _safe_str(op.get("imageUrl")).strip()
        if not image_url:
            continue
        if re.match(r"^https?://", image_url, flags=re.IGNORECASE):
            continue
        p = Path(image_url)
        if not p.is_absolute():
            p = (base_dir / p).resolve()
        image_path_map[image_id] = p
        image_meta_map[image_id] = op
    return image_path_map, image_meta_map


def _collect_sources(content: Dict) -> List[SourceItem]:
    items: List[SourceItem] = []
    for field in _iter_field_items(content):
        key_desc = _safe_str(field.get("keyDesc")).strip() or _safe_str(field.get("key")).strip()
        for src in field.get("sourceList", []):
            if not isinstance(src, dict):
                continue
            items.append(
                SourceItem(
                    image_id=_safe_str(src.get("imageId")).strip(),
                    key_desc=key_desc,
                    value=_safe_str(src.get("originalValue") or src.get("sepValue") or field.get("value")).strip(),
                    axis_x=_safe_int(src.get("axisX")),
                    axis_y=_safe_int(src.get("axisY")),
                    width=max(1, _safe_int(src.get("width"), 1)),
                    height=max(1, _safe_int(src.get("height"), 1)),
                    pdf_page=_safe_int(src.get("pdfPage")) if src.get("pdfPage") is not None else None,
                    match_level=_safe_str(src.get("matchLevel")).strip(),
                    coord_corrected=bool(src.get("coordCorrected", False)),
                    source_type=_safe_str(src.get("sourceType")).strip(),
                )
            )
    return items


def _load_font(size: int = 14) -> ImageFont.ImageFont:
    root = Path(__file__).resolve().parents[2]
    candidates = [
        root / "wzh" / "excel" / "fonts" / "wqy-zenhei.ttc",
        root / "wzh" / "excel" / "fonts" / "NotoSansCJK-Regular.ttc",
    ]
    for path in candidates:
        if path.exists():
            try:
                return ImageFont.truetype(str(path), size=size)
            except Exception:
                continue
    return ImageFont.load_default()


def _draw_label(draw: ImageDraw.ImageDraw, font: ImageFont.ImageFont, x: int, y: int, text: str, color):
    left, top, right, bottom = draw.textbbox((x, y), text, font=font)
    draw.rectangle((left - 2, top - 1, right + 2, bottom + 1), fill=(255, 255, 255))
    draw.text((x, y), text, fill=color, font=font)


def _overlap_ratio(a: Tuple[int, int, int, int], b: Tuple[int, int, int, int]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0
    inter = (ix2 - ix1) * (iy2 - iy1)
    area = max(1, (ax2 - ax1) * (ay2 - ay1))
    return inter / float(area)


def _extract_pdf_words(pdf_path: Path, image_meta_map: Dict[str, Dict]) -> Dict[int, List[Tuple[str, Tuple[int, int, int, int]]]]:
    try:
        import fitz  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise ImportError("Need PyMuPDF for PDF text cross-check: pip install pymupdf") from exc

    doc = fitz.open(str(pdf_path))
    page_words: Dict[int, List[Tuple[str, Tuple[int, int, int, int]]]] = {}
    try:
        for page_idx in range(doc.page_count):
            page_words[page_idx] = []
            page = doc[page_idx]
            for word in page.get_text("words"):
                if len(word) < 5:
                    continue
                x0, y0, x1, y1, text = word[:5]
                text = _safe_str(text).strip()
                if not text:
                    continue
                page_words[page_idx].append((text, (int(x0), int(y0), int(x1), int(y1))))
    finally:
        doc.close()

    # Convert PDF point boxes to image pixel boxes using operateImage scale.
    page_scaled_words: Dict[int, List[Tuple[str, Tuple[int, int, int, int]]]] = {}
    # choose one image meta for each page to get scale; page -> (scaleX, scaleY)
    page_scale: Dict[int, Tuple[float, float]] = {}
    for meta in image_meta_map.values():
        if meta.get("pdfDocPage") is None:
            continue
        page_idx = _safe_int(meta.get("pdfDocPage"))
        if page_idx in page_scale:
            continue
        sx = float(meta.get("scaleX", 1.0) or 1.0)
        sy = float(meta.get("scaleY", 1.0) or 1.0)
        page_scale[page_idx] = (sx, sy)

    for page_idx, words in page_words.items():
        sx, sy = page_scale.get(page_idx, (1.0, 1.0))
        scaled: List[Tuple[str, Tuple[int, int, int, int]]] = []
        for text, (x0, y0, x1, y1) in words:
            scaled.append(
                (
                    text,
                    (
                        int(round(x0 * sx)),
                        int(round(y0 * sy)),
                        int(round(x1 * sx)),
                        int(round(y1 * sy)),
                    ),
                )
            )
        page_scaled_words[page_idx] = scaled
    return page_scaled_words


def validate_and_visualize(
    output_json: Path,
    output_dir: Path,
    report_json: Path,
    pdf_path: Optional[Path] = None,
) -> Dict:
    with open(output_json, "r", encoding="utf-8") as f:
        data = json.load(f)
    content = data.get("content", {})
    image_path_map, image_meta_map = _build_image_map(content, output_json.parent)
    sources = _collect_sources(content)

    issues: List[Issue] = []

    # basic checks: image existence + bbox validity
    for src in sources:
        if not src.image_id:
            issues.append(Issue("error", src.image_id, src.key_desc, "missing imageId"))
            continue
        if src.image_id not in image_path_map:
            issues.append(Issue("error", src.image_id, src.key_desc, "imageId not found in operateImage"))
            continue
        image_path = image_path_map[src.image_id]
        if not image_path.exists():
            issues.append(Issue("error", src.image_id, src.key_desc, f"image file not found: {image_path}"))
            continue
        w = _safe_int(image_meta_map[src.image_id].get("imageWidth"), 0)
        h = _safe_int(image_meta_map[src.image_id].get("imageHeight"), 0)
        x1, y1, x2, y2 = src.box
        if src.width <= 0 or src.height <= 0:
            issues.append(Issue("error", src.image_id, src.key_desc, "non-positive width/height"))
        if x1 < 0 or y1 < 0 or x2 > max(1, w) or y2 > max(1, h):
            issues.append(Issue("warn", src.image_id, src.key_desc, f"bbox out of image bounds: {src.box} vs {w}x{h}"))
        if src.coord_corrected and src.source_type == "pdf_word" and not src.value:
            issues.append(Issue("warn", src.image_id, src.key_desc, "coordCorrected=true but value is empty"))

    # optional PDF source-text cross-check
    pdf_words = None
    if pdf_path:
        pdf_words = _extract_pdf_words(pdf_path, image_meta_map)
        for src in sources:
            if src.pdf_page is None:
                continue
            words = pdf_words.get(src.pdf_page, [])
            if not words:
                issues.append(Issue("warn", src.image_id, src.key_desc, f"no words on pdf page {src.pdf_page}"))
                continue
            overlapped = [w for w in words if _overlap_ratio(src.box, w[1]) > 0.05]
            if src.coord_corrected and src.source_type == "pdf_word" and not overlapped:
                issues.append(Issue("warn", src.image_id, src.key_desc, "corrected as pdf_word but no overlapped words"))
                continue
            if src.value:
                norm_val = normalize_text(src.value)
                ok_text = any(
                    normalize_text(w[0]) == norm_val
                    or (norm_val and norm_val in normalize_text(w[0]))
                    or (norm_val and normalize_text(w[0]) in norm_val)
                    for w in overlapped
                )
                if src.coord_corrected and src.source_type == "pdf_word" and not ok_text:
                    issues.append(Issue("warn", src.image_id, src.key_desc, "value mismatch with overlapped PDF words"))

    # visualization
    output_dir.mkdir(parents=True, exist_ok=True)
    font = _load_font()
    colors = {
        "ok": (34, 139, 34),
        "warn": (255, 140, 0),
        "err": (220, 20, 60),
        "model": (30, 144, 255),
    }

    issues_by_image: Dict[str, List[Issue]] = {}
    for issue in issues:
        issues_by_image.setdefault(issue.image_id, []).append(issue)

    sources_by_image: Dict[str, List[SourceItem]] = {}
    for src in sources:
        sources_by_image.setdefault(src.image_id, []).append(src)

    exported = 0
    for image_id, image_path in image_path_map.items():
        if not image_path.exists():
            continue
        image = Image.open(image_path).convert("RGB")
        draw = ImageDraw.Draw(image)
        image_issues = issues_by_image.get(image_id, [])
        srcs = sources_by_image.get(image_id, [])

        for src in srcs:
            has_src_issue = any(i.key_desc == src.key_desc for i in image_issues)
            if has_src_issue:
                color = colors["warn"]
            elif src.source_type == "model_box":
                color = colors["model"]
            else:
                color = colors["ok"]

            x1, y1, x2, y2 = src.box
            draw.rectangle((x1, y1, x2, y2), outline=color, width=2)
            tag = f"{src.key_desc}: {src.value or '<empty>'} [{src.match_level}]"
            if src.coord_corrected:
                tag += " [C]"
            else:
                tag += " [M]"
            _draw_label(draw, font, x1 + 2, max(0, y1 - 18), tag[:90], color)

        # image-level issue summary
        if image_issues:
            summary = f"issues={len(image_issues)}"
            _draw_label(draw, font, 8, 8, summary, colors["err"])

        out_name = f"{image_path.stem}_check.png"
        out_path = output_dir / out_name
        image.save(out_path)
        exported += 1
        print(f"[OK] imageId={image_id}, fields={len(srcs)}, issues={len(image_issues)}, saved={out_path}")

    report = {
        "outputJson": str(output_json),
        "pdfPath": str(pdf_path) if pdf_path else None,
        "summary": {
            "totalSources": len(sources),
            "totalImages": len(image_path_map),
            "exportedImages": exported,
            "errors": sum(1 for i in issues if i.level == "error"),
            "warnings": sum(1 for i in issues if i.level == "warn"),
            "infos": sum(1 for i in issues if i.level == "info"),
        },
        "issues": [
            {
                "level": i.level,
                "imageId": i.image_id,
                "keyDesc": i.key_desc,
                "message": i.message,
            }
            for i in issues
        ],
    }

    with open(report_json, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"[OK] validation report: {report_json}")
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="校验 PDF pipeline output.json 并导出可视化图片")
    parser.add_argument("--output_json", required=True, help="Path to output.json")
    parser.add_argument("--pdf_path", default="", help="Optional source PDF path for text cross-check")
    parser.add_argument("--output_dir", default="", help="Visualization output dir (default: <output_json_stem>_check_viz)")
    parser.add_argument("--report_json", default="", help="Validation report path (default: <output_json_stem>_check_report.json)")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_json = Path(args.output_json).resolve()
    if not output_json.exists():
        raise FileNotFoundError(f"output_json not found: {output_json}")

    output_dir = Path(args.output_dir).resolve() if args.output_dir else output_json.parent / f"{output_json.stem}_check_viz"
    report_json = Path(args.report_json).resolve() if args.report_json else output_json.parent / f"{output_json.stem}_check_report.json"
    pdf_path = Path(args.pdf_path).resolve() if args.pdf_path else None
    if pdf_path and not pdf_path.exists():
        raise FileNotFoundError(f"pdf_path not found: {pdf_path}")

    report = validate_and_visualize(
        output_json=output_json,
        output_dir=output_dir,
        report_json=report_json,
        pdf_path=pdf_path,
    )
    print("[DONE]", json.dumps(report["summary"], ensure_ascii=False))


if __name__ == "__main__":
    main()

