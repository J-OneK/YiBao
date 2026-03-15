"""CLI entry for declaration Excel processing pipeline."""

from __future__ import annotations

import argparse
import asyncio
import json
import importlib.util
import logging
import os
from pathlib import Path
import sys
from typing import Dict, List, Optional

if __package__ in (None, ""):
    # Support direct execution: python main.py ...
    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from jyk.excel_decl_pipeline.aligner import align_and_correct
    from jyk.excel_decl_pipeline.excel_loader import load_workbook_model
    from jyk.excel_decl_pipeline.models import Chunk
    from jyk.excel_decl_pipeline.output_builder import build_ocr_json
    from jyk.excel_decl_pipeline.prompt_adapter import generate_prompt
    from jyk.excel_decl_pipeline.qwen_client import recognize_chunks
    from jyk.excel_decl_pipeline.renderer import render_sheet
    from jyk.excel_decl_pipeline.splitter import split_rendered_sheet
else:
    from .aligner import align_and_correct
    from .excel_loader import load_workbook_model
    from .models import Chunk
    from .output_builder import build_ocr_json
    from .prompt_adapter import generate_prompt
    from .qwen_client import recognize_chunks
    from .renderer import render_sheet
    from .splitter import split_rendered_sheet

logger = logging.getLogger(__name__)


def _load_dotenv_files() -> None:
    """
    Auto-load environment variables from common .env locations.
    """
    candidates = [
        Path.cwd() / ".env",
        Path(__file__).resolve().parent / ".env",
        Path(__file__).resolve().parents[1] / ".env",
        Path(__file__).resolve().parents[2] / ".env",
        Path(__file__).resolve().parents[2] / "public" / "归档" / "customs_ocr" / ".env",
        Path(__file__).resolve().parents[2] / "jyk" / "归档" / "customs_ocr" / ".env",
    ]

    loaded_any = False
    try:
        from dotenv import load_dotenv

        for env_path in candidates:
            if env_path.exists():
                load_dotenv(dotenv_path=env_path, override=False)
                loaded_any = True
    except Exception:
        # Graceful fallback without python-dotenv dependency.
        for env_path in candidates:
            if not env_path.exists():
                continue
            loaded_any = True
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
    if loaded_any:
        logger.debug("Loaded environment variables from .env files.")


def _load_api_key_from_settings() -> Optional[str]:
    """
    Fallback: read API_KEY from existing customs_ocr settings.py files.
    """
    root = Path(__file__).resolve().parents[2]
    settings_paths = [
        root / "public" / "归档" / "customs_ocr" / "config" / "settings.py",
        root / "jyk" / "归档" / "customs_ocr" / "config" / "settings.py",
    ]
    for path in settings_paths:
        if not path.exists():
            continue
        try:
            spec = importlib.util.spec_from_file_location("excel_decl_pipeline_settings", str(path))
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
    fallback_key = _load_api_key_from_settings()
    if fallback_key:
        os.environ["API_KEY"] = fallback_key
        return fallback_key
    raise ValueError("Missing API key. Set environment variable DASHSCOPE_API_KEY or API_KEY.")


def _build_chunks(workbook, max_side: int, chunk_dir: Path) -> List[Chunk]:
    chunk_dir.mkdir(parents=True, exist_ok=True)
    chunks: List[Chunk] = []
    image_id = 1

    for sheet_index, sheet in enumerate(workbook.sheets):
        rendered = render_sheet(sheet, sheet_index=sheet_index)
        split_chunks = split_rendered_sheet(
            rendered=rendered,
            max_side=max_side,
            image_id_start=image_id,
            chunk_output_dir=chunk_dir,
        )
        chunks.extend(split_chunks)
        image_id += len(split_chunks)

    return chunks


async def run_pipeline_async(
    *,
    excel_path: str,
    att_type_code: int,
    output_json: str,
    model: str,
    api_base_url: str,
    max_side: int,
    workers: int,
) -> Dict:
    workbook = load_workbook_model(excel_path)
    output_path = Path(output_json)
    chunk_dir = output_path.parent / f"{output_path.stem}_chunks"

    logger.info("Rendering and splitting workbook...")
    chunks = _build_chunks(workbook, max_side=max_side, chunk_dir=chunk_dir)
    if not chunks:
        raise ValueError("No chunks generated from workbook.")
    logger.info("Generated %s chunk images.", len(chunks))

    prompt = generate_prompt(att_type_code)
    api_key = _resolve_api_key()
    logger.info("Calling Qwen model %s on %s chunks...", model, len(chunks))
    extractions = await recognize_chunks(
        chunks=chunks,
        prompt=prompt,
        att_type_code=att_type_code,
        model=model,
        api_key=api_key,
        api_base_url=api_base_url,
        workers=workers,
    )

    logger.info("Aligning fields with Excel cells and correcting coordinates...")
    aggregated = align_and_correct(extractions=extractions, att_type_code=att_type_code)

    logger.info("Building OCR-compatible JSON output...")
    output_data = build_ocr_json(aggregated=aggregated, chunks=chunks, att_type_code=att_type_code)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    logger.info("Pipeline completed. Output written to %s", output_path)
    return output_data


def run_pipeline(**kwargs) -> Dict:
    return asyncio.run(run_pipeline_async(**kwargs))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="报关单 Excel 处理流水线")
    parser.add_argument("--excel_path", required=True, help="Input Excel path (.xls/.xlsx)")
    parser.add_argument("--att_type_code", required=True, type=int, help="Document att_type_code")
    parser.add_argument("--output_json", required=True, help="Output OCR-compatible JSON path")
    parser.add_argument("--model", default="qwen3-vl-flash", help="Qwen vision model")
    parser.add_argument(
        "--api_base_url",
        default="https://dashscope.aliyuncs.com/compatible-mode/v1",
        help="OpenAI-compatible base URL",
    )
    parser.add_argument("--max_side", default=4096, type=int, help="Max chunk width/height")
    parser.add_argument("--workers", default=4, type=int, help="Concurrent OCR workers")
    parser.add_argument("--log_level", default="INFO", help="Log level: DEBUG/INFO/WARNING/ERROR")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    run_pipeline(
        excel_path=args.excel_path,
        att_type_code=args.att_type_code,
        output_json=args.output_json,
        model=args.model,
        api_base_url=args.api_base_url,
        max_side=args.max_side,
        workers=args.workers,
    )


if __name__ == "__main__":
    main()
