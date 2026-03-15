"""Load field mapping definitions from existing customs_ocr modules."""

from __future__ import annotations

import importlib.util
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Tuple


def _candidate_paths() -> List[Path]:
    root = Path(__file__).resolve().parents[2]
    return [
        root / "jyk" / "归档" / "customs_ocr" / "config" / "field_mapping.py",
        root / "public" / "归档" / "customs_ocr" / "config" / "field_mapping.py",
    ]


@lru_cache(maxsize=1)
def _load_mapping_module():
    for path in _candidate_paths():
        if path.exists():
            spec = importlib.util.spec_from_file_location("excel_decl_field_mapping", str(path))
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                return module
    raise FileNotFoundError("Cannot locate field_mapping.py in jyk/public customs_ocr directories.")


def get_fields_for_type(att_type_code: int) -> Tuple[List[str], List[str]]:
    module = _load_mapping_module()
    if hasattr(module, "get_fields_for_type"):
        head_fields, list_fields = module.get_fields_for_type(att_type_code)
        return list(head_fields), list(list_fields)
    return [], []


def get_key_desc_to_key() -> Dict[str, str]:
    module = _load_mapping_module()
    return dict(getattr(module, "KEY_DESC_TO_KEY", {}))


def fuzzy_match_key_desc(key_desc: str) -> str:
    module = _load_mapping_module()
    if hasattr(module, "fuzzy_match_key_desc"):
        return module.fuzzy_match_key_desc(key_desc)
    return get_key_desc_to_key().get(key_desc, "")


def get_att_type_name(att_type_code: int) -> str:
    module = _load_mapping_module()
    names = getattr(module, "ATT_TYPE_NAMES", {})
    return names.get(att_type_code, f"文档类型{att_type_code}")


def get_att_type_name_en(att_type_code: int) -> str:
    module = _load_mapping_module()
    names = getattr(module, "ATT_TYPE_NAMES_EN", {})
    return names.get(att_type_code, "ExcelChunk")

