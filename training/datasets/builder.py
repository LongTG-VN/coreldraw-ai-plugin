"""Validated, license-aware smoke dataset materialization."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from training.adapters.base import DesignAdapter
from training.datasets.splitter import SplitName, deterministic_split
from training.schemas.design import DesignDocument


@dataclass(frozen=True)
class BuildResult:
    output_dir: Path
    total: int
    split_counts: dict[SplitName, int]
    metadata_path: Path


def materialize_dataset(
    rows: Iterable[dict[str, Any]],
    adapter: DesignAdapter,
    output_dir: Path,
    *,
    limit: int,
    seed: int = 42,
) -> BuildResult:
    if limit < 1 or limit > 500:
        raise ValueError("smoke dataset limit must be between 1 and 500")

    documents: dict[SplitName, list[DesignDocument]] = {
        "train": [],
        "validation": [],
        "test": [],
    }
    sample_ids: set[str] = set()
    normalization_warning_count = 0
    for index, row in enumerate(rows):
        if index >= limit:
            break
        document = adapter.convert(row, index)
        if document.sample_id in sample_ids:
            raise ValueError(f"duplicate sample_id: {document.sample_id}")
        sample_ids.add(document.sample_id)
        warnings = document.metadata.get("normalization_warnings", [])
        if isinstance(warnings, list):
            normalization_warning_count += len(warnings)
        split = deterministic_split(document.sample_id, seed=seed)
        documents[split].append(document)

    total = sum(len(values) for values in documents.values())
    if total == 0:
        raise ValueError("dataset source yielded no samples")

    output_dir.mkdir(parents=True, exist_ok=True)
    for split, records in documents.items():
        path = output_dir / f"{split}.jsonl"
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            for document in records:
                handle.write(document.model_dump_json(exclude_none=True) + "\n")

    first = next(records[0] for records in documents.values() if records)
    split_counts: dict[SplitName, int] = {
        split: len(records) for split, records in documents.items()
    }
    metadata = {
        "schema_version": "0.1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": first.source.name,
        "source_split": first.source.split,
        "license_class": first.source.license_class,
        "commercial_allowed": first.source.commercial_allowed,
        "seed": seed,
        "requested_limit": limit,
        "total": total,
        "splits": split_counts,
        "split_method": "sha256(seed:sample_id)",
        "normalization_warning_count": normalization_warning_count,
    }
    metadata_path = output_dir / "metadata.json"
    metadata_path.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return BuildResult(output_dir, total, split_counts, metadata_path)
