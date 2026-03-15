"""JSON parsing helpers for Qwen responses."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional


def _remove_markdown(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```json\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^```\s*", "", text)
    text = re.sub(r"\s*```\s*$", "", text)
    return text.strip()


def _extract_json(text: str) -> Optional[str]:
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    return None


def _normalize_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                if "text" in item:
                    parts.append(str(item["text"]))
                elif "content" in item:
                    parts.append(str(item["content"]))
            else:
                parts.append(str(item))
        return "\n".join(parts)
    return str(content)


def parse_and_validate(content: Any) -> Optional[Dict[str, Any]]:
    raw = _normalize_content(content)
    candidates = [raw, _remove_markdown(raw)]
    extracted = _extract_json(raw)
    if extracted:
        candidates.append(extracted)

    for candidate in candidates:
        if not candidate:
            continue
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if validate_structure(data):
            return data
    return None


def validate_structure(data: Dict[str, Any]) -> bool:
    if not isinstance(data, dict):
        return False
    if "preDecHead" not in data or "preDecList" not in data:
        return False
    if not isinstance(data["preDecHead"], list):
        return False
    if not isinstance(data["preDecList"], list):
        return False

    for item in data["preDecHead"]:
        if not _validate_field_item(item):
            return False
    for row in data["preDecList"]:
        if not isinstance(row, list):
            return False
        for item in row:
            if not _validate_field_item(item):
                return False
    return True


def _validate_field_item(item: Dict[str, Any]) -> bool:
    if not isinstance(item, dict):
        return False
    if "keyDesc" not in item or "value" not in item or "pixel" not in item:
        return False
    pixel = item["pixel"]
    if not isinstance(pixel, list) or len(pixel) != 4:
        return False
    for coord in pixel:
        if not isinstance(coord, (int, float)):
            return False
    return True

