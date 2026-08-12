from __future__ import annotations

import json
import math
from pathlib import Path

import pytest
from PIL import Image, UnidentifiedImageError

from training.inference.preview import render_preview
from training.retrieval import (
    HybridReferenceRetriever,
    HybridRetrievalWeights,
    JsonlReferenceProvider,
    ReferenceMetadataV1,
    ReferenceRecordV1,
    RetrievalLeakageExclusions,
    VisualEmbeddingCache,
    VisualEmbeddingIndex,
    analyze_brief,
    build_visual_index,
    cosine_similarity,
    embedding_cache_key,
    extract_reference_features,
    normalize_embedding,
    summarize_reference,
)
from training.retrieval.visual_embeddings import VisualEmbeddingError
from training.tools.build_reference_corpus import _generic_document


class FakeVisualEmbedder:
    model_id = "fixture/visual"
    revision = "abc123"
    license_name = "Apache-2.0"
    dimension = 4
    preprocessing_identity = "fixture_rgb_v1"
    device = "cpu"
    loaded = False
    load_duration_seconds = 0.0
    peak_memory_gib = 0.0

    def __init__(self, vectors: dict[str, list[float]] | None = None) -> None:
        self.vectors = vectors or {}
        self.calls = 0

    def embed_image(self, path: Path) -> list[float]:
        self.calls += 1
        try:
            with Image.open(path) as image:
                image.verify()
        except (UnidentifiedImageError, OSError) as exc:
            raise VisualEmbeddingError("corrupt fixture image") from exc
        return normalize_embedding(self.vectors.get(path.stem, [1, 0, 0, 0]))

    def embed_images(self, paths: list[Path]) -> list[list[float]]:
        return [self.embed_image(path) for path in paths]

    def embed_text(self, text: str) -> list[float]:
        self.calls += 1
        lowered = text.casefold()
        if "spa" in lowered:
            return normalize_embedding([1, 0, 0, 0])
        if "cafe" in lowered or "coffee" in lowered:
            return normalize_embedding([0, 1, 0, 0])
        return normalize_embedding([0, 0, 1, 0])


def _corpus(
    tmp_path: Path,
    definitions: list[tuple[str, str, str]],
) -> tuple[Path, dict[str, Path]]:
    root = tmp_path / "corpus"
    (root / "documents").mkdir(parents=True)
    (root / "previews").mkdir()
    rows = []
    previews = {}
    for reference_id, category, variant in definitions:
        document = _generic_document(category, variant, ["cream", "gold"])
        features = extract_reference_features(document)
        safe = reference_id.replace(":", "_")
        document_path = root / "documents" / f"{safe}.json"
        preview_path = root / "previews" / f"{safe}.png"
        document_path.write_text(document.model_dump_json(indent=2), encoding="utf-8")
        render_preview(document, preview_path, max_dimension=256)
        metadata = ReferenceMetadataV1(
            reference_id=reference_id,
            category=category,
            format="poster",
            aspect_ratio=float(features.aspect_ratio),
            style_tags=["minimal", variant],
            color_tags=["cream", "gold"],
            text_density=features.text_density,
            element_count=features.element_count,
            layout_features={"composition": features.composition},
            design_document_path=str(document_path.relative_to(root)),
            preview_path=str(preview_path.relative_to(root)),
            source="synthetic_owned",
            license="project_owned",
            license_class="production_safe",
            research_only=False,
            commercial_allowed=True,
            provenance={"template_family": f"family:{variant}"},
        )
        rows.append(
            ReferenceRecordV1(
                metadata=metadata,
                features=features,
                summary=summarize_reference(metadata, features),
            )
        )
        previews[reference_id] = preview_path
    index = root / "reference_index.jsonl"
    index.write_text("".join(row.model_dump_json() + "\n" for row in rows), encoding="utf-8")
    return index, previews


def _build(
    tmp_path: Path,
    definitions: list[tuple[str, str, str]],
    vectors: dict[str, list[float]],
) -> tuple[Path, VisualEmbeddingIndex, FakeVisualEmbedder, dict[str, Path]]:
    reference_index, previews = _corpus(tmp_path, definitions)
    embedder = FakeVisualEmbedder(
        {
            path.stem: vectors[reference_id]
            for reference_id, path in previews.items()
        }
    )
    output = tmp_path / "visual"
    build_visual_index(
        provider=JsonlReferenceProvider(reference_index),
        source_reference_index=reference_index,
        reference_root=reference_index.parent,
        output=output,
        embedder=embedder,
        cache=VisualEmbeddingCache(tmp_path / "cache"),
    )
    return reference_index, VisualEmbeddingIndex(output), embedder, previews


def test_normalization_cosine_and_cache_identity_are_content_addressed() -> None:
    vector = normalize_embedding([3, 4])
    assert vector == pytest.approx([.6, .8])
    assert cosine_similarity([1, 0], [0, 1]) == pytest.approx(0)
    assert math.sqrt(sum(value * value for value in vector)) == pytest.approx(1)
    base = dict(
        source_sha256="a" * 64,
        model_id="fixture",
        revision="one",
        preprocessing_identity="rgb_v1",
    )
    first = embedding_cache_key(**base)
    assert first != embedding_cache_key(**{**base, "source_sha256": "b" * 64})
    assert first != embedding_cache_key(**{**base, "revision": "two"})
    assert first != embedding_cache_key(**{**base, "preprocessing_identity": "rgb_v2"})


def test_image_text_embeddings_and_cache_do_not_use_path_identity(tmp_path: Path) -> None:
    first = tmp_path / "first.png"
    second = tmp_path / "second.png"
    Image.new("RGB", (16, 16), "#663399").save(first)
    second.write_bytes(first.read_bytes())
    embedder = FakeVisualEmbedder()
    cache = VisualEmbeddingCache(tmp_path / "cache")
    one, hit_one, key_one = cache.embed_image_cached(embedder, first)
    two, hit_two, key_two = cache.embed_image_cached(embedder, second)
    assert one == two
    assert hit_one is False
    assert hit_two is True
    assert key_one == key_two
    assert len(embedder.embed_text("spa poster")) == embedder.dimension


def test_missing_and_corrupt_images_fail_explicitly(tmp_path: Path) -> None:
    embedder = FakeVisualEmbedder()
    cache = VisualEmbeddingCache(tmp_path / "cache")
    with pytest.raises(FileNotFoundError):
        cache.embed_image_cached(embedder, tmp_path / "missing.png")
    corrupt = tmp_path / "corrupt.png"
    corrupt.write_bytes(b"not an image")
    with pytest.raises(VisualEmbeddingError, match="corrupt"):
        cache.embed_image_cached(embedder, corrupt)


def test_index_serialization_fingerprint_and_cosine_search(tmp_path: Path) -> None:
    _, index, _, _ = _build(
        tmp_path,
        [("template:spa:right", "spa", "hero_right"), ("template:cafe:left", "cafe", "hero_left")],
        {
            "template:spa:right": [1, 0, 0, 0],
            "template:cafe:left": [0, 1, 0, 0],
        },
    )
    assert index.manifest.reference_count == 2
    assert len(index.manifest.fingerprint) == 64
    assert index.search([1, 0, 0, 0], top_k=1)[0][0].reference_id == "template:spa:right"
    embeddings = index.root / index.manifest.embeddings_file
    embeddings.write_bytes(embeddings.read_bytes()[:-1] + b"x")
    with pytest.raises(ValueError, match="fingerprint"):
        VisualEmbeddingIndex(index.root)


def test_hybrid_global_pool_allows_adjacent_category_to_win(tmp_path: Path) -> None:
    reference_index, index, embedder, _ = _build(
        tmp_path,
        [("template:spa:grid", "spa", "grid"), ("template:my_pham:right", "my_pham", "hero_right")],
        {
            "template:spa:grid": [0, 1, 0, 0],
            "template:my_pham:right": [1, 0, 0, 0],
        },
    )
    retriever = HybridReferenceRetriever(
        JsonlReferenceProvider(reference_index),
        visual_index=index,
        embedder=embedder,
        weights=HybridRetrievalWeights(structural=.10, visual_text=.90, visual_asset=0),
        mmr_lambda=1,
    )
    results = retriever.retrieve_references(
        analyze_brief("Poster spa premium", width=210, height=297),
        top_k=2,
    )
    assert results[0].metadata.category == "my_pham"
    assert {item.metadata.category for item in results} == {"spa", "my_pham"}
    assert results[0].visual_text_score > results[1].visual_text_score


def test_leakage_near_duplicate_and_leave_one_family_out(tmp_path: Path) -> None:
    reference_index, index, embedder, previews = _build(
        tmp_path,
        [
            ("template:spa:right", "spa", "hero_right"),
            ("template:spa:left", "spa", "hero_left"),
            ("template:cafe:grid", "cafe", "grid"),
        ],
        {
            "template:spa:right": [1, 0, 0, 0],
            "template:spa:left": [0, 1, 0, 0],
            "template:cafe:grid": [0, 0, 1, 0],
        },
    )
    retriever = HybridReferenceRetriever(
        JsonlReferenceProvider(reference_index),
        visual_index=index,
        embedder=embedder,
    )
    results = retriever.retrieve_references(
        analyze_brief("spa poster", width=210, height=297),
        top_k=1,
        asset_paths=[previews["template:spa:right"]],
        exclusions=RetrievalLeakageExclusions(
            template_families=frozenset({"family:hero_left"}),
            near_duplicate_threshold=.99,
        ),
    )
    assert results[0].reference_id == "template:cafe:grid"
    assert retriever.last_diagnostics is not None
    excluded = retriever.last_diagnostics.excluded
    assert {item["reference_id"] for item in excluded} == {
        "template:spa:right",
        "template:spa:left",
    }


def test_visual_mmr_selects_different_template_families(tmp_path: Path) -> None:
    reference_index, index, embedder, _ = _build(
        tmp_path,
        [
            ("template:spa:right", "spa", "hero_right"),
            ("template:spa:right2", "spa", "centered"),
            ("template:spa:left", "spa", "hero_left"),
        ],
        {
            "template:spa:right": [1, 0, 0, 0],
            "template:spa:right2": [.999, .001, 0, 0],
            "template:spa:left": [0, 1, 0, 0],
        },
    )
    retriever = HybridReferenceRetriever(
        JsonlReferenceProvider(reference_index),
        visual_index=index,
        embedder=embedder,
        weights=HybridRetrievalWeights(structural=.2, visual_text=.8, visual_asset=0),
        mmr_lambda=.40,
    )
    results = retriever.retrieve_references(
        analyze_brief("spa poster", width=210, height=297),
        top_k=2,
    )
    assert len({item.template_family for item in results}) == 2
    assert results[1].visual_diversity > 0
