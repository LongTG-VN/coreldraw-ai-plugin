from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from training.retrieval import (
    EmptyReferenceCorpusError,
    JsonlReferenceProvider,
    ReferenceMetadataV1,
    ReferenceRecordV1,
    ReferenceRetriever,
    StructuredBriefV1,
    analyze_brief,
    build_reference_context,
    estimate_reference_tokens,
    extract_reference_features,
    summarize_reference,
)
from training.retrieval.providers import InternalCdrReferenceProvider
from training.tools.build_reference_corpus import (
    _generic_document,
    build_reference_corpus,
)


PROMPTS = (
    ("Poster spa cao cấp màu kem vàng tối giản", "spa", "poster"),
    ("Poster tiệm nail trẻ trung pastel", "nail", "poster"),
    ("Modern hair salon poster nền đen", "salon", "poster"),
    ("Poster khai trương quán cafe vintage", "cafe", "poster"),
    ("Social post trà sữa năng động", "tra_sua", "social_post"),
    ("Menu nhà hàng Việt gồm 6 món và giá", "nha_hang", "menu"),
    ("Poster mỹ phẩm serum tối giản", "my_pham", "poster"),
    ("Poster MEGA SALE 50% bold", "poster_sale", "poster"),
    ("Grand opening poster festive", "khai_truong", "poster"),
    ("Food menu quán ăn nhanh 10 món", "menu", "menu"),
    ("Business card kiến trúc sư", "card_visit", "business_card"),
    ("Bảng hiệu ngang cho cửa hàng", "bang_hieu", "signage"),
    ("Social banner workshop digital", "banner_social", "banner"),
)


@pytest.mark.parametrize(("prompt", "category", "format_name"), PROMPTS)
def test_brief_analyzer_covers_benchmark_categories(
    prompt: str,
    category: str,
    format_name: str,
) -> None:
    brief = analyze_brief(prompt, width=108, height=135)

    assert brief.category == category
    assert brief.format == format_name
    assert brief.fallback_used is False
    assert brief.aspect_ratio == pytest.approx(0.8)


def test_brief_analyzer_is_strict_and_has_fallback() -> None:
    fallback = analyze_brief("Create a balanced information layout", width=100, height=100)

    assert fallback.category == "general"
    assert fallback.format == "poster"
    assert fallback.fallback_used is True
    with pytest.raises(ValidationError):
        StructuredBriefV1.model_validate(
            {**fallback.model_dump(), "aspect_ratio": "1.0"}
        )
    with pytest.raises(ValueError, match="prompt cannot be empty"):
        analyze_brief(" ", width=100, height=100)


def _record(category: str, variant: str, *, reference_id: str | None = None) -> ReferenceRecordV1:
    variant_info = {
        "centered": (["minimal", "balanced"], ["cream", "gold"]),
        "split": (["modern", "asymmetric"], ["green", "cream"]),
        "grid": (["editorial", "structured"], ["red", "white"]),
        "hero_left": (["bold", "dynamic"], ["blue", "purple"]),
        "hero_right": (["luxury", "clean"], ["black", "gold"]),
    }
    styles, colors = variant_info[variant]
    document = _generic_document(category, variant, colors)
    features = extract_reference_features(document)
    ref_id = reference_id or f"fixture:{category}:{variant}"
    format_name = str(document.metadata["format"])
    metadata = ReferenceMetadataV1(
        reference_id=ref_id,
        category=category,
        format=format_name,
        aspect_ratio=float(features.aspect_ratio),
        style_tags=styles,
        color_tags=colors,
        text_density=features.text_density,
        element_count=features.element_count,
        layout_features={"composition": features.composition},
        design_document_path=f"documents/{ref_id}.json",
        preview_path=f"previews/{ref_id}.png",
        source="synthetic_owned",
        license="project_owned",
        license_class="production_safe",
        research_only=False,
        commercial_allowed=True,
        provenance={"fixture": True},
    )
    return ReferenceRecordV1(
        metadata=metadata,
        features=features,
        summary=summarize_reference(metadata, features),
    )


class MemoryProvider:
    provider_name = "memory"

    def __init__(self, records: list[ReferenceRecordV1]) -> None:
        self.records = records

    def load_references(self) -> list[ReferenceRecordV1]:
        return list(self.records)


def test_feature_extraction_is_reproducible_and_complete() -> None:
    document = _generic_document("spa", "split", ["green", "cream"])
    first = extract_reference_features(document)
    second = extract_reference_features(document)

    assert first == second
    assert first.element_count == 5
    assert first.text_count == 4
    assert first.image_count == 0
    assert len(first.normalized_element_boxes) == 5
    assert {"headline", "body", "cta", "hero"} <= set(first.element_roles)
    assert first.hero_position is not None
    assert first.cta_position is not None
    assert 0 <= first.whitespace <= 1
    assert first.aspect_ratio > 0
    assert first.composition_regions
    assert first.dominant_colors
    assert first.headline_body_ratio >= 1


def test_reference_metadata_rejects_missing_and_unsafe_license_flags() -> None:
    record = _record("spa", "centered")
    payload = record.metadata.model_dump()
    payload.pop("license")
    with pytest.raises(ValidationError):
        ReferenceMetadataV1.model_validate(payload)

    payload = record.metadata.model_dump()
    payload.update(research_only=True, commercial_allowed=True)
    with pytest.raises(ValidationError, match="research-only"):
        ReferenceMetadataV1.model_validate(payload)


def test_weighted_retrieval_is_explainable_deterministic_and_diverse() -> None:
    records = [_record("spa", variant) for variant in ("centered", "split", "grid", "hero_left", "hero_right")]
    records.append(_record("menu", "grid"))
    retriever = ReferenceRetriever(MemoryProvider(records))
    brief = analyze_brief(
        "Poster spa cao cấp màu kem vàng tối giản",
        width=100,
        height=140,
    )

    first = retriever.retrieve_references(brief, top_k=4)
    second = retriever.retrieve_references(brief, top_k=4)

    assert first == second
    assert len(first) == 4
    assert all(item.metadata.category == "spa" for item in first)
    assert all(0 <= item.score <= 1 for item in first)
    assert all(item.match.category == 1 for item in first)
    assert len({item.summary.composition for item in first}) >= 3
    assert any(item.match.diversity < 1 for item in first[1:])


def test_empty_corpus_and_category_fallback() -> None:
    empty = ReferenceRetriever(MemoryProvider([]))
    brief = analyze_brief("Poster spa", width=100, height=140)
    with pytest.raises(EmptyReferenceCorpusError, match="empty"):
        empty.retrieve_references(brief)

    fallback_brief = analyze_brief("Balanced information poster", width=100, height=140)
    results = ReferenceRetriever(
        MemoryProvider([_record("spa", "centered"), _record("menu", "grid")])
    ).retrieve_references(fallback_brief, top_k=2)
    assert results
    assert all(item.fallback_reason == "no_matching_category_used_format" for item in results)


def test_jsonl_provider_validates_duplicates_and_invalid_rows(tmp_path: Path) -> None:
    record = _record("spa", "centered")
    valid_path = tmp_path / "index.jsonl"
    valid_path.write_text(record.model_dump_json() + "\n", encoding="utf-8")
    assert JsonlReferenceProvider(valid_path).load_references() == [record]

    valid_path.write_text(
        record.model_dump_json() + "\n" + record.model_dump_json() + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate reference_id"):
        JsonlReferenceProvider(valid_path).load_references()
    valid_path.write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid reference record"):
        JsonlReferenceProvider(valid_path).load_references()


def test_internal_cdr_provider_is_explicitly_disabled() -> None:
    with pytest.raises(RuntimeError, match="disabled"):
        InternalCdrReferenceProvider().load_references()


def test_reference_summary_and_context_respect_token_budget() -> None:
    brief = analyze_brief("Poster spa cao cấp", width=100, height=140)
    results = ReferenceRetriever(
        MemoryProvider([_record("spa", variant) for variant in ("centered", "split", "grid")])
    ).retrieve_references(brief, top_k=3)

    context = build_reference_context(results, max_tokens=500)

    assert context.references
    assert context.estimated_tokens <= 500
    assert estimate_reference_tokens(context.model_dump(exclude_none=True)) > 0
    assert all(len(item.hierarchy) <= 6 for item in context.references)
    assert "do not copy text" in context.instruction


def test_corpus_builder_writes_provenance_previews_and_mixed_license(
    tmp_path: Path,
) -> None:
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    research = _generic_document("spa", "centered", ["cream", "gold"])
    payload = research.model_dump()
    payload["sample_id"] = "genposter100k:fixture"
    payload["source"] = {
        "name": "genposter100k",
        "split": "train",
        "license_class": "research_only",
        "upstream_id": "fixture",
        "commercial_allowed": False,
    }
    payload["metadata"]["license"] = "CC-BY-NC-4.0"
    research = type(research).model_validate(payload)
    (source_dir / "train.jsonl").write_text(
        research.model_dump_json(exclude_none=True) + "\n",
        encoding="utf-8",
    )

    output_dir = tmp_path / "corpus"
    manifest = build_reference_corpus(source_dir, output_dir, genposter_limit=1)
    records = JsonlReferenceProvider(output_dir / "reference_index.jsonl").load_references()

    assert manifest["research_only"] is True
    assert manifest["commercial_allowed"] is False
    assert manifest["source_counts"] == {
        "genposter100k": 1,
        "project_owned_structural_templates": 65,
    }
    assert len(records) == 66
    genposter = next(item for item in records if item.metadata.source == "genposter100k")
    assert genposter.metadata.research_only is True
    assert genposter.metadata.commercial_allowed is False
    assert (output_dir / genposter.metadata.design_document_path).is_file()
    assert (output_dir / genposter.metadata.preview_path).is_file()
    template = next(item for item in records if item.metadata.source == "synthetic_owned")
    template_document = json.loads(
        (output_dir / template.metadata.design_document_path).read_text(encoding="utf-8")
    )
    contents = [
        element["text"]["content"]
        for element in template_document["elements"]
        if element.get("text")
    ]
    assert "PRIMARY MESSAGE" in contents
    assert all("SPA AN NHIÊN" not in value for value in contents)
