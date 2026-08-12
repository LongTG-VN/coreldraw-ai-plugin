"""Replaceable local reference corpus providers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol, runtime_checkable

from training.retrieval.models import ReferenceRecordV1


@runtime_checkable
class ReferenceProvider(Protocol):
    provider_name: str

    def load_references(self) -> list[ReferenceRecordV1]: ...


class JsonlReferenceProvider:
    provider_name = "jsonl"

    def __init__(self, index_path: Path) -> None:
        self.index_path = index_path.resolve()

    def load_references(self) -> list[ReferenceRecordV1]:
        if not self.index_path.is_file():
            raise FileNotFoundError(f"reference index does not exist: {self.index_path}")
        records: list[ReferenceRecordV1] = []
        seen: set[str] = set()
        with self.index_path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    record = ReferenceRecordV1.model_validate_json(line)
                except Exception as exc:
                    raise ValueError(
                        f"invalid reference record at {self.index_path}:{line_number}: {exc}"
                    ) from exc
                reference_id = record.metadata.reference_id
                if reference_id in seen:
                    raise ValueError(f"duplicate reference_id: {reference_id}")
                seen.add(reference_id)
                records.append(record)
        return records


class InternalCdrReferenceProvider:
    """Future boundary for approved private CDR-derived references."""

    provider_name = "internal_cdr"

    def __init__(self, index_path: Path | None = None, *, enabled: bool = False) -> None:
        self.index_path = index_path
        self.enabled = enabled

    def load_references(self) -> list[ReferenceRecordV1]:
        if not self.enabled:
            raise RuntimeError(
                "internal_cdr retrieval is disabled until the approved archive is normalized"
            )
        if self.index_path is None:
            raise ValueError("internal_cdr index_path is required when enabled")
        return JsonlReferenceProvider(self.index_path).load_references()
