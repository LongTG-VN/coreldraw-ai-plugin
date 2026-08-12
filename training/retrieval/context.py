"""Compact, bounded reference context for the planner."""

from __future__ import annotations

import json
import math

from training.retrieval.models import (
    ReferenceContextV1,
    ReferenceDesignSummaryV1,
    ReferenceRetrievalResultV1,
)


REFERENCE_INSTRUCTION = (
    "Use these references only as structural inspiration. Synthesize a new layout; "
    "do not copy text, brands, assets, or exact coordinates. Preserve the user brief."
)


def estimate_reference_tokens(value: object) -> int:
    """Conservative tokenizer-free estimate suitable for a hard local budget."""

    serialized = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return math.ceil(len(serialized.encode("utf-8")) / 3.2)


def build_reference_context(
    results: list[ReferenceRetrievalResultV1],
    *,
    max_tokens: int = 900,
) -> ReferenceContextV1:
    if max_tokens < 64:
        raise ValueError("reference context token budget must be at least 64")
    selected: list[ReferenceDesignSummaryV1] = []
    truncated = False
    for result in results:
        candidate = selected + [result.summary]
        payload = {
            "instruction": REFERENCE_INSTRUCTION,
            "references": [
                item.model_dump(exclude_none=True, exclude_defaults=True)
                for item in candidate
            ],
        }
        if estimate_reference_tokens(payload) > max_tokens:
            truncated = True
            break
        selected = candidate
    final_payload = {
        "instruction": REFERENCE_INSTRUCTION,
        "references": [
            item.model_dump(exclude_none=True, exclude_defaults=True)
            for item in selected
        ],
    }
    return ReferenceContextV1(
        instruction=REFERENCE_INSTRUCTION,
        references=selected,
        estimated_tokens=estimate_reference_tokens(final_payload),
        truncated=truncated,
    )
