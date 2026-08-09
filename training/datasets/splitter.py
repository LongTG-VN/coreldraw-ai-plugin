"""Order-independent deterministic dataset splitting."""

from __future__ import annotations

import hashlib
from typing import Literal


SplitName = Literal["train", "validation", "test"]


def deterministic_split(
    sample_id: str,
    *,
    seed: int = 42,
    train_ratio: float = 0.8,
    validation_ratio: float = 0.1,
) -> SplitName:
    if not sample_id:
        raise ValueError("sample_id cannot be empty")
    if train_ratio <= 0 or validation_ratio < 0:
        raise ValueError("split ratios must be non-negative")
    if train_ratio + validation_ratio >= 1:
        raise ValueError("train_ratio + validation_ratio must be less than 1")

    digest = hashlib.sha256(f"{seed}:{sample_id}".encode("utf-8")).digest()
    bucket = int.from_bytes(digest[:8], "big") / float(2**64)
    if bucket < train_ratio:
        return "train"
    if bucket < train_ratio + validation_ratio:
        return "validation"
    return "test"
