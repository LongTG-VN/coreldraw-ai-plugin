"""Deterministic identity and integrity checks for local model generations."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat


class GenerationIdentityV1(BaseModel):
    """Everything that can materially change one raw planner response."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    original_prompt_sha256: str = Field(min_length=64, max_length=64)
    grounded_prompt_sha256: str = Field(min_length=64, max_length=64)
    reference_context_sha256: str = Field(min_length=16, max_length=64)
    reference_ids: list[str]
    width_mm: FiniteFloat = Field(gt=0)
    height_mm: FiniteFloat = Field(gt=0)
    seed: int = Field(ge=0)
    generation_config: dict[str, bool | int | float]
    model_id: str = Field(min_length=1)
    model_revision: str = Field(min_length=1)
    checkpoint_sha256: str = Field(min_length=64, max_length=64)

    def canonical_json(self) -> str:
        return json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    @property
    def identity_sha256(self) -> str:
        return sha256_text(self.canonical_json())


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fingerprint_checkpoint(path: Path) -> str:
    """Hash checkpoint contents without depending on its machine-local path."""

    root = path.resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"checkpoint directory does not exist: {root}")
    files = sorted(item for item in root.rglob("*") if item.is_file())
    if not files:
        raise ValueError(f"checkpoint directory contains no files: {root}")
    digest = hashlib.sha256()
    for file_path in files:
        relative = file_path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(file_path.stat().st_size).encode("ascii"))
        digest.update(b"\0")
        digest.update(sha256_file(file_path).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def generation_config_from_kwargs(kwargs: dict[str, Any]) -> dict[str, bool | int | float]:
    fields = (
        "max_new_tokens",
        "do_sample",
        "temperature",
        "top_p",
        "top_k",
        "repetition_penalty",
    )
    missing = [field for field in fields if field not in kwargs]
    if missing:
        raise ValueError(f"generation identity is missing config fields: {missing}")
    return {field: kwargs[field] for field in fields}


def build_generation_identity(
    *,
    original_prompt: str,
    grounded_prompt: str,
    reference_context_hash: str,
    reference_ids: list[str],
    width_mm: float,
    height_mm: float,
    seed: int,
    generation_config: dict[str, bool | int | float],
    model_id: str,
    model_revision: str,
    checkpoint_sha256: str,
) -> GenerationIdentityV1:
    return GenerationIdentityV1(
        original_prompt_sha256=sha256_text(original_prompt),
        grounded_prompt_sha256=sha256_text(grounded_prompt),
        reference_context_sha256=reference_context_hash,
        reference_ids=list(reference_ids),
        width_mm=width_mm,
        height_mm=height_mm,
        seed=seed,
        generation_config=generation_config,
        model_id=model_id,
        model_revision=model_revision,
        checkpoint_sha256=checkpoint_sha256,
    )


__all__ = [
    "GenerationIdentityV1",
    "build_generation_identity",
    "fingerprint_checkpoint",
    "generation_config_from_kwargs",
    "sha256_file",
    "sha256_text",
]
