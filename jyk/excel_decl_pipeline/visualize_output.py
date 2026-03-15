"""Visualize OCR output boxes on chunk images.

Usage:
    python jyk/excel_decl_pipeline/visualize_output.py \
      --output_json d:/code/YiBao/jyk/excel_decl_pipeline/output.json
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont


COLORS: List[Tuple[int, int, int]] = [
    (220, 20, 60),
    (30, 144, 255),
    (34, 139, 34),
    (255, 140, 0),
    (138, 43, 226),
    (0, 139, 139),
    (178, 34, 34),
    (218, 165, 32),
    (70, 130, 180),
    (199, 21, 133),
]


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


def _safe_int(value, default: int = 0) -> int:
    try:
        return int(round(float(value)))
    except Exception:
        return default


def _safe_str(value) -> str:
    return "" if value is None else str(value)


def _flatten_operate_image(raw) -> List[Dict]:
    if not isinstance(raw, list):
        return []
    result: List[Dict] = []
    for item in raw:
        if isinstance(item, dict):
            result.append(item)
        elif isinstance(item, list):
            for sub in item:
                if isinstance(sub, dict):
                    result.append(sub)
    return result


def _iter_field_items(content: Dict) -> Iterable[Dict]:
    for item in content.get("preDecHead", []):
        if isinstance(item, dict):
            yield item
    for row in content.get("preDecList", []):
        if not isinstance(row, list):
            continue
        for item in row:
            if isinstance(item, dict):
                yield item
    for row in content.get("preDecContainer", []):
        if not isinstance(row, list):
            continue
        for item in row:
            if isinstance(item, dict):
                yield item


def _build_image_map(content: Dict, base_dir: Path) -> Dict[str, Path]:
    image_map: Dict[str, Path] = {}
    for item in _flatten_operate_image(content.get("operateImage", [])):
        image_id = _safe_str(item.get("imageId")).strip()
        image_url = _safe_str(item.get("imageUrl")).strip()
        if not image_id or not image_url:
            continue
        if re.match(r"^https?://", image_url, flags=re.IGNORECASE):
            # Only local files are supported in this visualization script.
            continue
        p = Path(image_url)
        if not p.is_absolute():
            p = (base_dir / p).resolve()
        image_map[image_id] = p
    return image_map


def _extract_box(source: Dict) -> Optional[Tuple[int, int, int, int]]:
    x = source.get("axisX")
    y = source.get("axisY")
    w = source.get("width")
    h = source.get("height")

    if x is not None and y is not None and w is not None and h is not None:
        x1 = _safe_int(x)
        y1 = _safe_int(y)
        ww = max(1, _safe_int(w))
        hh = max(1, _safe_int(h))
        return (x1, y1, x1 + ww, y1 + hh)

    # Compatible fallback with start/end style coordinates.
    sx = source.get("startx")
    sy = source.get("starty")
    ex = source.get("endx")
    ey = source.get("endy")
    if sx is not None and sy is not None and ex is not None and ey is not None:
        x1 = _safe_int(sx)
        y1 = _safe_int(sy)
        x2 = _safe_int(ex)
        y2 = _safe_int(ey)
        return (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))
    return None


def _build_annotations(content: Dict, max_label_len: int) -> Dict[str, List[Dict]]:
    result: Dict[str, List[Dict]] = {}
    for field in _iter_field_items(content):
        key_desc = _safe_str(field.get("keyDesc")).strip() or _safe_str(field.get("key")).strip()
        for source in field.get("sourceList", []):
            if not isinstance(source, dict):
                continue
            image_id = _safe_str(source.get("imageId")).strip()
            if not image_id:
                continue
            box = _extract_box(source)
            if not box:
                continue

            value = _safe_str(source.get("originalValue") or source.get("sepValue") or field.get("value")).strip()
            label = f"{key_desc}: {value}" if value else key_desc
            if len(label) > max_label_len:
                label = label[: max_label_len - 1] + "…"

            ann = {
                "box": box,
                "label": label,
                "matchLevel": _safe_str(source.get("matchLevel")),
                "coordCorrected": bool(source.get("coordCorrected", False)),
            }
            result.setdefault(image_id, []).append(ann)
    return result


def _draw_label(draw: ImageDraw.ImageDraw, font: ImageFont.ImageFont, x: int, y: int, text: str, color):
    left, top, right, bottom = draw.textbbox((x, y), text, font=font)
    draw.rectangle((left - 2, top - 1, right + 2, bottom + 1), fill=(255, 255, 255))
    draw.text((x, y), text, fill=color, font=font)


def visualize_output(output_json: Path, output_dir: Path, max_label_len: int = 42, line_width: int = 2) -> int:
    with open(output_json, "r", encoding="utf-8") as f:
        data = json.load(f)

    content = data.get("content", {})
    image_map = _build_image_map(content, output_json.parent)
    annotations = _build_annotations(content, max_label_len=max_label_len)

    if not image_map:
        print("No local images found under content.operateImage.imageUrl")
        return 0

    output_dir.mkdir(parents=True, exist_ok=True)
    font = _load_font()
    exported = 0

    for image_id, image_path in image_map.items():
        if not image_path.exists():
            print(f"[Skip] imageId={image_id}: image not found -> {image_path}")
            continue

        image = Image.open(image_path).convert("RGB")
        draw = ImageDraw.Draw(image)
        anns = annotations.get(image_id, [])

        for idx, ann in enumerate(anns):
            color = COLORS[idx % len(COLORS)]
            x1, y1, x2, y2 = ann["box"]
            draw.rectangle((x1, y1, x2, y2), outline=color, width=line_width)

            tag = ann["label"]
            if ann["matchLevel"]:
                tag += f" [{ann['matchLevel']}]"
            if ann["coordCorrected"]:
                tag += " [C]"
            else:
                tag += " [M]"
            _draw_label(draw, font, x1 + 2, max(0, y1 - 18), tag, color)

        out_name = f"{image_path.stem}_viz.png"
        out_path = output_dir / out_name
        image.save(out_path)
        exported += 1
        print(f"[OK] imageId={image_id}, boxes={len(anns)}, saved={out_path}")

    return exported


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="将 output.json 中的坐标框绘制到对应图片上")
    parser.add_argument("--output_json", required=True, help="Pipeline output JSON path")
    parser.add_argument(
        "--output_dir",
        default="",
        help="Visualization output directory (default: <output_json_stem>_viz)",
    )
    parser.add_argument("--max_label_len", type=int, default=42, help="Max label characters")
    parser.add_argument("--line_width", type=int, default=2, help="Rectangle line width")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_json = Path(args.output_json).resolve()
    if not output_json.exists():
        raise FileNotFoundError(f"output_json not found: {output_json}")

    if args.output_dir:
        output_dir = Path(args.output_dir).resolve()
    else:
        output_dir = output_json.parent / f"{output_json.stem}_viz"

    exported = visualize_output(
        output_json=output_json,
        output_dir=output_dir,
        max_label_len=max(10, args.max_label_len),
        line_width=max(1, args.line_width),
    )
    print(f"Done. Exported {exported} visualization images to: {output_dir}")


if __name__ == "__main__":
    main()

