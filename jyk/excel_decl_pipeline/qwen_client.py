"""Async Qwen3-VL recognizer for Excel chunks."""

from __future__ import annotations

import asyncio
import logging
from typing import List, Optional, Sequence

from openai import AsyncOpenAI

from .field_mapping_loader import fuzzy_match_key_desc, get_fields_for_type
from .json_utils import parse_and_validate
from .models import Chunk, ChunkExtraction, RecognizedField

logger = logging.getLogger(__name__)


def _normalize_pixel(pixel: Sequence[float]) -> List[int]:
    coords: List[int] = []
    for raw in pixel[:4]:
        try:
            value = int(round(float(raw)))
        except Exception:
            value = 0
        coords.append(max(0, min(999, value)))
    while len(coords) < 4:
        coords.append(0)
    return coords


def _parse_field_item(item: dict, area: str, source_image_id: int, model_row_index: Optional[int] = None):
    key_desc = str(item.get("keyDesc", "")).strip()
    if not key_desc:
        return None
    key = fuzzy_match_key_desc(key_desc)
    if not key:
        return None
    value = "" if item.get("value") is None else str(item.get("value"))
    pixel = _normalize_pixel(item.get("pixel", [0, 0, 0, 0]))
    return RecognizedField(
        key_desc=key_desc,
        key=key,
        value=value,
        pixel=pixel,
        area=area,
        source_image_id=source_image_id,
        model_row_index=model_row_index,
    )


async def _recognize_single_chunk(
    client: AsyncOpenAI,
    chunk: Chunk,
    prompt: str,
    model: str,
    max_retries: int,
    head_allowed_keys: set,
    list_allowed_keys: set,
) -> ChunkExtraction:
    extraction = ChunkExtraction(chunk=chunk)

    for attempt in range(1, max_retries + 1):
        try:
            response = await client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": chunk.image_data_url}},
                            {"type": "text", "text": prompt},
                        ],
                    }
                ],
                extra_body={"enable_thinking": False, "thinking_budget": 81920},
            )
            parsed = parse_and_validate(response.choices[0].message.content)
            if not parsed:
                continue

            for item in parsed.get("preDecHead", []):
                field = _parse_field_item(item, "head", chunk.image_id)
                if not field:
                    continue
                if field.key not in head_allowed_keys:
                    continue
                extraction.pre_dec_head.append(field)

            for idx, row in enumerate(parsed.get("preDecList", [])):
                row_fields: List[RecognizedField] = []
                for item in row:
                    field = _parse_field_item(item, "list", chunk.image_id, model_row_index=idx)
                    if not field:
                        continue
                    if field.key not in list_allowed_keys:
                        continue
                    row_fields.append(field)
                if row_fields:
                    extraction.pre_dec_list.append(row_fields)
            return extraction
        except Exception as exc:
            logger.warning(
                "chunk %s recognition failed on attempt %s/%s: %s",
                chunk.chunk_id,
                attempt,
                max_retries,
                exc,
            )
            await asyncio.sleep(min(0.5 * attempt, 2.0))

    return extraction


async def recognize_chunks(
    chunks: List[Chunk],
    prompt: str,
    att_type_code: int,
    model: str,
    api_key: str,
    api_base_url: str,
    workers: int = 4,
    max_retries: int = 3,
) -> List[ChunkExtraction]:
    head_fields, list_fields = get_fields_for_type(att_type_code)
    head_allowed_keys = {fuzzy_match_key_desc(name) for name in head_fields}
    list_allowed_keys = {fuzzy_match_key_desc(name) for name in list_fields}
    head_allowed_keys.discard("")
    list_allowed_keys.discard("")

    client = AsyncOpenAI(api_key=api_key, base_url=api_base_url)
    semaphore = asyncio.Semaphore(max(1, workers))

    async def _run(chunk: Chunk) -> ChunkExtraction:
        async with semaphore:
            return await _recognize_single_chunk(
                client=client,
                chunk=chunk,
                prompt=prompt,
                model=model,
                max_retries=max_retries,
                head_allowed_keys=head_allowed_keys,
                list_allowed_keys=list_allowed_keys,
            )

    tasks = [_run(chunk) for chunk in chunks]
    return await asyncio.gather(*tasks)
