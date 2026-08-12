"""Lazy local image/text embeddings with content-addressed cache identity."""

from __future__ import annotations

import hashlib
import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol, runtime_checkable

from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict, Field


DEFAULT_VISUAL_MODEL_ID = "google/siglip2-base-patch16-224"
DEFAULT_VISUAL_MODEL_REVISION = "75de2d55ec2d0b4efc50b3e9ad70dba96a7b2fa2"
DEFAULT_VISUAL_MODEL_LICENSE = "Apache-2.0"
DEFAULT_VISUAL_DIMENSION = 768
DEFAULT_PREPROCESSING = "siglip2_auto_processor_224_exif_v1"


class VisualEmbeddingError(RuntimeError):
    pass


class StrictEmbeddingModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class VisualEmbeddingRecordV1(StrictEmbeddingModel):
    schema_version: str = "1.0"
    vector: list[float] = Field(min_length=1)
    embedding_model: str = Field(min_length=1)
    revision: str = Field(min_length=1)
    dimension: int = Field(gt=0)
    preprocessing_identity: str = Field(min_length=1)
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    created_at: str = Field(min_length=1)
    latency_seconds: float = Field(ge=0)


@runtime_checkable
class VisualEmbedder(Protocol):
    model_id: str
    revision: str
    license_name: str
    dimension: int
    preprocessing_identity: str
    device: str
    loaded: bool
    load_duration_seconds: float | None
    peak_memory_gib: float

    def embed_image(self, path: Path) -> list[float]: ...
    def embed_images(self, paths: list[Path]) -> list[list[float]]: ...
    def embed_text(self, text: str) -> list[float]: ...


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_embedding(values: list[float]) -> list[float]:
    if not values or not all(math.isfinite(value) for value in values):
        raise VisualEmbeddingError("embedding must contain finite values")
    norm = math.sqrt(sum(value * value for value in values))
    if norm <= 1e-12:
        raise VisualEmbeddingError("embedding norm must be positive")
    return [value / norm for value in values]


def cosine_similarity(first: list[float], second: list[float]) -> float:
    if len(first) != len(second) or not first:
        raise ValueError("cosine vectors must have the same positive dimension")
    left = normalize_embedding(first)
    right = normalize_embedding(second)
    return max(-1.0, min(1.0, sum(a * b for a, b in zip(left, right))))


def embedding_cache_key(
    *,
    source_sha256: str,
    model_id: str,
    revision: str,
    preprocessing_identity: str,
) -> str:
    if len(source_sha256) != 64:
        raise ValueError("source_sha256 must be a SHA-256 hex digest")
    payload = json.dumps(
        {
            "source_sha256": source_sha256,
            "model_id": model_id,
            "revision": revision,
            "preprocessing_identity": preprocessing_identity,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class VisualEmbeddingCache:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def path_for(self, key: str) -> Path:
        if len(key) != 64 or any(char not in "0123456789abcdef" for char in key):
            raise ValueError("cache key must be lowercase SHA-256")
        return self.root / key[:2] / f"{key}.json"

    def load(self, key: str) -> VisualEmbeddingRecordV1 | None:
        path = self.path_for(key)
        if not path.is_file():
            return None
        return VisualEmbeddingRecordV1.model_validate_json(
            path.read_text(encoding="utf-8")
        )

    def save(self, key: str, record: VisualEmbeddingRecordV1) -> Path:
        path = self.path_for(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            record.model_dump_json(indent=2) + "\n",
            encoding="utf-8",
        )
        return path

    def embed_image_cached(
        self,
        embedder: VisualEmbedder,
        path: Path,
    ) -> tuple[list[float], bool, str]:
        resolved = path.resolve()
        if not resolved.is_file():
            raise FileNotFoundError(f"visual embedding image missing: {resolved}")
        source_hash = sha256_file(resolved)
        key = embedding_cache_key(
            source_sha256=source_hash,
            model_id=embedder.model_id,
            revision=embedder.revision,
            preprocessing_identity=embedder.preprocessing_identity,
        )
        cached = self.load(key)
        if cached is not None:
            if cached.dimension != embedder.dimension:
                raise VisualEmbeddingError("cached embedding dimension mismatch")
            return normalize_embedding(cached.vector), True, key
        started = time.perf_counter()
        vector = normalize_embedding(embedder.embed_image(resolved))
        elapsed = time.perf_counter() - started
        self.save(
            key,
            VisualEmbeddingRecordV1(
                vector=vector,
                embedding_model=embedder.model_id,
                revision=embedder.revision,
                dimension=len(vector),
                preprocessing_identity=embedder.preprocessing_identity,
                source_sha256=source_hash,
                created_at=datetime.now(timezone.utc).isoformat(),
                latency_seconds=elapsed,
            ),
        )
        return vector, False, key


class TransformersSiglip2Embedder:
    """Lazy SigLIP2 adapter; importing this module never loads torch or weights."""

    model_id = DEFAULT_VISUAL_MODEL_ID
    revision = DEFAULT_VISUAL_MODEL_REVISION
    license_name = DEFAULT_VISUAL_MODEL_LICENSE
    dimension = DEFAULT_VISUAL_DIMENSION
    preprocessing_identity = DEFAULT_PREPROCESSING

    def __init__(
        self,
        *,
        model_id: str = DEFAULT_VISUAL_MODEL_ID,
        revision: str = DEFAULT_VISUAL_MODEL_REVISION,
        device: str = "auto",
    ) -> None:
        self.model_id = model_id
        self.revision = revision
        self.device = device
        self.loaded = False
        self.load_duration_seconds: float | None = None
        self.peak_memory_gib = 0.0
        self._model = None
        self._processor = None
        self._torch = None

    def _ensure_loaded(self) -> None:
        if self.loaded:
            return
        started = time.perf_counter()
        try:
            import torch
            from transformers import AutoModel, AutoProcessor
        except ImportError as exc:
            raise VisualEmbeddingError(
                "visual embedding requires the optional torch/transformers training stack"
            ) from exc
        selected = (
            "cuda" if self.device == "auto" and torch.cuda.is_available() else self.device
        )
        if selected == "auto":
            selected = "cpu"
        dtype = torch.float16 if selected == "cuda" else torch.float32
        try:
            processor = AutoProcessor.from_pretrained(
                self.model_id,
                revision=self.revision,
            )
            model = AutoModel.from_pretrained(
                self.model_id,
                revision=self.revision,
                dtype=dtype,
                low_cpu_mem_usage=True,
            ).eval()
            model.to(selected)
        except Exception as exc:
            raise VisualEmbeddingError(
                f"failed to load {self.model_id}@{self.revision}: {exc}"
            ) from exc
        self._torch = torch
        self._processor = processor
        self._model = model
        self.device = selected
        self.loaded = True
        self.load_duration_seconds = time.perf_counter() - started
        if selected == "cuda":
            torch.cuda.reset_peak_memory_stats()

    def _vectors(self, tensor: object) -> list[list[float]]:
        assert self._torch is not None
        if not hasattr(tensor, "float"):
            tensor = getattr(tensor, "pooler_output", None)
        if tensor is None or not hasattr(tensor, "float"):
            raise VisualEmbeddingError(
                "SigLIP2 feature output has no tensor or pooler_output"
            )
        normalized = self._torch.nn.functional.normalize(tensor.float(), dim=-1)
        rows = normalized.detach().cpu().tolist()
        if any(len(row) != self.dimension for row in rows):
            raise VisualEmbeddingError("unexpected SigLIP2 embedding dimension")
        if self.device == "cuda":
            self.peak_memory_gib = max(
                self.peak_memory_gib,
                self._torch.cuda.max_memory_allocated() / 1024**3,
            )
        return [normalize_embedding([float(value) for value in row]) for row in rows]

    def embed_images(self, paths: list[Path]) -> list[list[float]]:
        if not paths:
            return []
        self._ensure_loaded()
        assert self._processor is not None and self._model is not None and self._torch is not None
        images = []
        try:
            for path in paths:
                with Image.open(path.resolve()) as source:
                    images.append(ImageOps.exif_transpose(source).convert("RGB"))
        except (FileNotFoundError, UnidentifiedImageError, OSError) as exc:
            raise VisualEmbeddingError(f"invalid visual embedding image: {exc}") from exc
        inputs = self._processor(images=images, return_tensors="pt")
        inputs = {key: value.to(self.device) for key, value in inputs.items()}
        with self._torch.inference_mode():
            features = self._model.get_image_features(**inputs)
        return self._vectors(features)

    def embed_image(self, path: Path) -> list[float]:
        return self.embed_images([path])[0]

    def embed_text(self, text: str) -> list[float]:
        if not text.strip():
            raise ValueError("visual embedding text cannot be empty")
        self._ensure_loaded()
        assert self._processor is not None and self._model is not None and self._torch is not None
        inputs = self._processor(
            text=[text],
            padding="max_length",
            max_length=64,
            truncation=True,
            return_tensors="pt",
        )
        inputs = {key: value.to(self.device) for key, value in inputs.items()}
        with self._torch.inference_mode():
            features = self._model.get_text_features(**inputs)
        return self._vectors(features)[0]


__all__ = [
    "DEFAULT_PREPROCESSING",
    "DEFAULT_VISUAL_DIMENSION",
    "DEFAULT_VISUAL_MODEL_ID",
    "DEFAULT_VISUAL_MODEL_LICENSE",
    "DEFAULT_VISUAL_MODEL_REVISION",
    "TransformersSiglip2Embedder",
    "VisualEmbedder",
    "VisualEmbeddingCache",
    "VisualEmbeddingError",
    "VisualEmbeddingRecordV1",
    "cosine_similarity",
    "embedding_cache_key",
    "normalize_embedding",
    "sha256_file",
]
