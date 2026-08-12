"""Portable float32 visual index for hundreds or thousands of references."""

from __future__ import annotations

import hashlib
import json
import struct
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from training.retrieval.features import extract_reference_features, summarize_reference
from training.retrieval.models import ReferenceDesignSummaryV1
from training.retrieval.providers import ReferenceProvider
from training.retrieval.visual_embeddings import (
    VisualEmbedder,
    VisualEmbeddingCache,
    cosine_similarity,
    normalize_embedding,
    sha256_file,
)
from training.schemas.design import DesignDocument


class StrictVisualIndexModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class VisualIndexRecordV1(StrictVisualIndexModel):
    schema_version: str = "1.0"
    reference_id: str = Field(min_length=1)
    offset: int = Field(ge=0)
    dimension: int = Field(gt=0)
    preview_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    preview_path: str = Field(min_length=1)
    source: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    template_family: str = Field(min_length=1)
    license: str = Field(min_length=1)
    research_only: bool
    commercial_allowed: bool
    summary: ReferenceDesignSummaryV1


class VisualEmbeddingIndexV1(StrictVisualIndexModel):
    schema_version: str = "1.0"
    visual_index_id: str = Field(min_length=1)
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    embedding_model: str = Field(min_length=1)
    embedding_revision: str = Field(min_length=1)
    embedding_license: str = Field(min_length=1)
    dimension: int = Field(gt=0)
    preprocessing_identity: str = Field(min_length=1)
    reference_count: int = Field(ge=0)
    preview_count: int = Field(ge=0)
    missing_preview_count: int = Field(ge=0)
    records_file: str = "visual_index.jsonl"
    embeddings_file: str = "visual_embeddings.f32"
    records_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    embeddings_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_reference_index: str = Field(min_length=1)
    source_reference_index_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    created_at: str = Field(min_length=1)


def template_family(reference_id: str, provenance: dict[str, Any]) -> str:
    explicit = provenance.get("template_family")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()
    parts = reference_id.split(":")
    if reference_id.startswith("template:") and len(parts) >= 3:
        return f"template:{parts[-1]}"
    return str(provenance.get("sample_id") or reference_id)


def _source_id(reference_id: str, provenance: dict[str, Any]) -> str:
    return str(
        provenance.get("upstream_id")
        or provenance.get("sample_id")
        or reference_id
    )


def _fingerprint_payload(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class VisualIndexBuildResult:
    manifest: VisualEmbeddingIndexV1
    build_report: dict[str, Any]


def build_visual_index(
    *,
    provider: ReferenceProvider,
    source_reference_index: Path,
    reference_root: Path,
    output: Path,
    embedder: VisualEmbedder,
    cache: VisualEmbeddingCache,
) -> VisualIndexBuildResult:
    started = time.perf_counter()
    source_reference_index = source_reference_index.resolve()
    reference_root = reference_root.resolve()
    output = output.resolve()
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"visual index output must be new or empty: {output}")
    output.mkdir(parents=True, exist_ok=True)
    records = sorted(
        provider.load_references(),
        key=lambda item: item.metadata.reference_id,
    )
    if not records:
        raise ValueError("visual index requires at least one reference")
    index_records: list[VisualIndexRecordV1] = []
    vectors: list[list[float]] = []
    missing: list[dict[str, str]] = []
    cache_hits = 0
    embedding_seconds = 0.0
    for record in records:
        metadata = record.metadata
        preview = (reference_root / metadata.preview_path).resolve()
        try:
            preview.relative_to(reference_root)
        except ValueError as exc:
            raise ValueError(f"preview path escapes reference root: {preview}") from exc
        if not preview.is_file():
            missing.append(
                {"reference_id": metadata.reference_id, "preview_path": str(preview)}
            )
            continue
        embedding_started = time.perf_counter()
        vector, hit, _ = cache.embed_image_cached(embedder, preview)
        embedding_seconds += time.perf_counter() - embedding_started
        cache_hits += int(hit)
        if len(vector) != embedder.dimension:
            raise ValueError(f"dimension mismatch for {metadata.reference_id}")
        design_path = (reference_root / metadata.design_document_path).resolve()
        summary = record.summary
        if design_path.is_file():
            document = DesignDocument.model_validate_json(
                design_path.read_text(encoding="utf-8")
            )
            features = extract_reference_features(document)
            summary = summarize_reference(metadata, features, include_visual=True)
        index_records.append(
            VisualIndexRecordV1(
                reference_id=metadata.reference_id,
                offset=len(vectors) * embedder.dimension,
                dimension=embedder.dimension,
                preview_sha256=sha256_file(preview),
                preview_path=metadata.preview_path,
                source=metadata.source,
                source_id=_source_id(metadata.reference_id, metadata.provenance),
                template_family=template_family(
                    metadata.reference_id,
                    metadata.provenance,
                ),
                license=metadata.license,
                research_only=metadata.research_only,
                commercial_allowed=metadata.commercial_allowed,
                summary=summary,
            )
        )
        vectors.append(normalize_embedding(vector))
    if not vectors:
        raise ValueError("visual index has no usable previews")
    records_path = output / "visual_index.jsonl"
    records_path.write_text(
        "".join(item.model_dump_json() + "\n" for item in index_records),
        encoding="utf-8",
    )
    embeddings_path = output / "visual_embeddings.f32"
    with embeddings_path.open("wb") as handle:
        for vector in vectors:
            handle.write(struct.pack(f"<{len(vector)}f", *vector))
    records_hash = sha256_file(records_path)
    embeddings_hash = sha256_file(embeddings_path)
    source_hash = sha256_file(source_reference_index)
    fingerprint = _fingerprint_payload(
        {
            "embedding_model": embedder.model_id,
            "embedding_revision": embedder.revision,
            "dimension": embedder.dimension,
            "preprocessing_identity": embedder.preprocessing_identity,
            "records_sha256": records_hash,
            "embeddings_sha256": embeddings_hash,
            "source_reference_index_sha256": source_hash,
        }
    )
    manifest = VisualEmbeddingIndexV1(
        visual_index_id=f"design_v0_3_4_visual:{fingerprint[:16]}",
        fingerprint=fingerprint,
        embedding_model=embedder.model_id,
        embedding_revision=embedder.revision,
        embedding_license=embedder.license_name,
        dimension=embedder.dimension,
        preprocessing_identity=embedder.preprocessing_identity,
        reference_count=len(index_records),
        preview_count=len(index_records),
        missing_preview_count=len(missing),
        records_sha256=records_hash,
        embeddings_sha256=embeddings_hash,
        source_reference_index=str(source_reference_index),
        source_reference_index_sha256=source_hash,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    manifest_path = output / "index_manifest.json"
    manifest_path.write_text(manifest.model_dump_json(indent=2) + "\n", encoding="utf-8")
    build_report = {
        "schema_version": "1.0",
        "reference_count": len(records),
        "preview_count": len(index_records),
        "missing_previews": missing,
        "cache_hits": cache_hits,
        "cache_misses": len(index_records) - cache_hits,
        "embedding_seconds": embedding_seconds,
        "build_duration_seconds": time.perf_counter() - started,
        "device": embedder.device,
        "model_load_seconds": embedder.load_duration_seconds,
        "peak_memory_gib": embedder.peak_memory_gib,
        "visual_index_id": manifest.visual_index_id,
        "fingerprint": manifest.fingerprint,
    }
    (output / "build_report.json").write_text(
        json.dumps(build_report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return VisualIndexBuildResult(manifest=manifest, build_report=build_report)


class VisualEmbeddingIndex:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        manifest_path = self.root / "index_manifest.json"
        if not manifest_path.is_file():
            raise FileNotFoundError(f"visual index manifest missing: {manifest_path}")
        self.manifest = VisualEmbeddingIndexV1.model_validate_json(
            manifest_path.read_text(encoding="utf-8")
        )
        records_path = self.root / self.manifest.records_file
        embeddings_path = self.root / self.manifest.embeddings_file
        if sha256_file(records_path) != self.manifest.records_sha256:
            raise ValueError("visual index records fingerprint mismatch")
        if sha256_file(embeddings_path) != self.manifest.embeddings_sha256:
            raise ValueError("visual index embeddings fingerprint mismatch")
        self.records = [
            VisualIndexRecordV1.model_validate_json(line)
            for line in records_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        expected_bytes = len(self.records) * self.manifest.dimension * 4
        data = embeddings_path.read_bytes()
        if len(data) != expected_bytes:
            raise ValueError("visual embedding binary size mismatch")
        self.vectors = [
            list(struct.unpack_from(f"<{self.manifest.dimension}f", data, item.offset * 4))
            for item in self.records
        ]
        self.by_id = {record.reference_id: index for index, record in enumerate(self.records)}
        if len(self.by_id) != len(self.records):
            raise ValueError("visual index contains duplicate reference IDs")

    def vector(self, reference_id: str) -> list[float]:
        try:
            return list(self.vectors[self.by_id[reference_id]])
        except KeyError as exc:
            raise KeyError(f"reference missing from visual index: {reference_id}") from exc

    def search(
        self,
        query: list[float],
        *,
        top_k: int = 5,
        allowed_ids: set[str] | None = None,
    ) -> list[tuple[VisualIndexRecordV1, float]]:
        if top_k < 1:
            raise ValueError("top_k must be positive")
        if len(query) != self.manifest.dimension:
            raise ValueError("query dimension does not match visual index")
        rows = [
            (record, cosine_similarity(query, self.vectors[index]))
            for index, record in enumerate(self.records)
            if allowed_ids is None or record.reference_id in allowed_ids
        ]
        rows.sort(key=lambda item: (-item[1], item[0].reference_id))
        return rows[:top_k]


__all__ = [
    "VisualEmbeddingIndex",
    "VisualEmbeddingIndexV1",
    "VisualIndexBuildResult",
    "VisualIndexRecordV1",
    "build_visual_index",
    "template_family",
]
