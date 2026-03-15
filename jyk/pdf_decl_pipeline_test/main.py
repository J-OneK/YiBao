"""CLI entry for PDF declaration pipeline test."""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import logging
import os
from pathlib import Path
import sys
from typing import Dict, Optional

if __package__ in (None, ""):
    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from jyk.excel_decl_pipeline.prompt_adapter import generate_prompt
    from jyk.pdf_decl_pipeline_test.aligner import align_and_correct_pdf
    from jyk.pdf_decl_pipeline_test.output_builder import build_ocr_json
    from jyk.pdf_decl_pipeline_test.pdf_loader import load_pdf_pages
    from jyk.pdf_decl_pipeline_test.qwen_client import recognize_pages
else:
    from jyk.excel_decl_pipeline.prompt_adapter import generate_prompt
    from .aligner import align_and_correct_pdf
    from .output_builder import build_ocr_json
    from .pdf_loader import load_pdf_pages
    from .qwen_client import recognize_pages

logger = logging.getLogger(__name__)


def _load_dotenv_files() -> None:
    candidates = [
        Path.cwd() / ".env",
        Path(__file__).resolve().parent / ".env",
        Path(__file__).resolve().parents[1] / ".env",
        Path(__file__).resolve().parents[2] / ".env",
        Path(__file__).resolve().parents[2] / "public" / "归档" / "customs_ocr" / ".env",
        Path(__file__).resolve().parents[2] / "jyk" / "归档" / "customs_ocr" / ".env",
    ]
    try:
        from dotenv import load_dotenv

        for env_path in candidates:
            if env_path.exists():
                load_dotenv(dotenv_path=env_path, override=False)
    except Exception:
        for env_path in candidates:
            if not env_path.exists():
                continue
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    if key and key not in os.environ:
                        os.environ[key] = value


def _load_api_key_from_settings() -> Optional[str]:
    root = Path(__file__).resolve().parents[2]
    settings_paths = [
        root / "public" / "归档" / "customs_ocr" / "config" / "settings.py",
        root / "jyk" / "归档" / "customs_ocr" / "config" / "settings.py",
    ]
    for path in settings_paths:
        if not path.exists():
            continue
        try:
            spec = importlib.util.spec_from_file_location("pdf_decl_pipeline_settings", str(path))
            if not spec or not spec.loader:
                continue
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            api_key = getattr(module, "API_KEY", None)
            if isinstance(api_key, str) and api_key.strip():
                return api_key.strip()
        except Exception:
            continue
    return None


def _resolve_api_key() -> str:
    _load_dotenv_files()
    for key_name in ("DASHSCOPE_API_KEY", "API_KEY"):
        value = os.getenv(key_name)
        if value:
            return value
    fallback = _load_api_key_from_settings()
    if fallback:
        return fallback
    raise ValueError("Missing API key. Set DASHSCOPE_API_KEY or API_KEY.")


async def run_pipeline_async(
    *,
    pdf_path: str,
    att_type_code: int,
    output_json: str,
    model: str,
    api_base_url: str,
    max_side: int,
    workers: int,
    dpi: int,
) -> Dict:
    output_path = Path(output_json)
    page_dir = output_path.parent / f"{output_path.stem}_pages"
    pages = load_pdf_pages(pdf_path=pdf_path, output_dir=page_dir, max_side=max_side, dpi=dpi)
    if not pages:
        raise ValueError("No pages rendered from PDF.")

    prompt = generate_prompt(att_type_code)
    api_key = _resolve_api_key()
    logger.info("Recognizing %s pages with %s ...", len(pages), model)
    extractions = await recognize_pages(
        pages=pages,
        prompt=prompt,
        att_type_code=att_type_code,
        model=model,
        api_key=api_key,
        api_base_url=api_base_url,
        workers=workers,
    )

    logger.info("Cross-validating with PDF words and correcting boxes...")
    aggregated = align_and_correct_pdf(extractions=extractions, att_type_code=att_type_code)
    output_data = build_ocr_json(aggregated=aggregated, pages=pages, att_type_code=att_type_code)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    logger.info("Output written to %s", output_path)
    return output_data


def run_pipeline(**kwargs) -> Dict:
    return asyncio.run(run_pipeline_async(**kwargs))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="PDF 源坐标交叉验证小测验")
    parser.add_argument("--pdf_path", required=True, help="Input PDF path")
    parser.add_argument("--att_type_code", required=True, type=int, help="Document att_type_code")
    parser.add_argument("--output_json", required=True, help="Output OCR-compatible JSON path")
    parser.add_argument("--model", default="qwen3-vl-flash", help="Qwen vision model")
    parser.add_argument(
        "--api_base_url",
        default="https://dashscope.aliyuncs.com/compatible-mode/v1",
        help="OpenAI-compatible base URL",
    )
    parser.add_argument("--max_side", default=4096, type=int, help="Max page image side length")
    parser.add_argument("--workers", default=4, type=int, help="Concurrent OCR workers")
    parser.add_argument("--dpi", default=216, type=int, help="PDF render DPI")
    parser.add_argument("--log_level", default="INFO", help="Log level")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        run_pipeline(
            pdf_path=args.pdf_path,
            att_type_code=args.att_type_code,
            output_json=args.output_json,
            model=args.model,
            api_base_url=args.api_base_url,
            max_side=args.max_side,
            workers=args.workers,
            dpi=args.dpi,
        )
    except ImportError as exc:
        logger.error(str(exc))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
