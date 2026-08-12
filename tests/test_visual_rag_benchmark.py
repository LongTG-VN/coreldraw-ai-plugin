from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from training.retrieval import ReferenceMetadataV1, ReferenceRecordV1
from training.retrieval.features import extract_reference_features, summarize_reference
from training.tools.benchmark_visual_retrieval import _asset_paths, _filtered, _metrics
from training.tools.build_reference_corpus import _generic_document


def _record(reference_id: str, category: str, source: str) -> ReferenceRecordV1:
    document = _generic_document(category, "hero_right", ["cream", "gold"])
    features = extract_reference_features(document)
    metadata = ReferenceMetadataV1(
        reference_id=reference_id,
        category=category,
        format="poster",
        aspect_ratio=float(features.aspect_ratio),
        style_tags=["minimal"],
        color_tags=["cream"],
        text_density=features.text_density,
        element_count=features.element_count,
        design_document_path="documents/example.json",
        preview_path="previews/example.png",
        source=source,
        license="fixture",
        license_class="research_only" if source == "genposter100k" else "production_safe",
        research_only=source == "genposter100k",
        commercial_allowed=source != "genposter100k",
    )
    return ReferenceRecordV1(
        metadata=metadata,
        features=features,
        summary=summarize_reference(metadata, features),
    )


def test_held_out_filters_remove_exact_template_without_hiding_adjacent_categories() -> None:
    rows = [
        _record("template:spa:right", "spa", "synthetic_owned"),
        _record("template:cosmetics:right", "my_pham", "synthetic_owned"),
        _record("genposter:0001", "cafe", "genposter100k"),
    ]
    held_out = _filtered(rows, "exclude_exact_category_templates", "spa")
    assert {row.metadata.reference_id for row in held_out} == {
        "template:cosmetics:right",
        "genposter:0001",
    }
    assert [row.metadata.reference_id for row in _filtered(rows, "genposter_only", "spa")] == [
        "genposter:0001"
    ]


def test_asset_query_uses_visual_asset_before_logo(tmp_path: Path) -> None:
    Image.new("RGB", (32, 24), "#663399").save(tmp_path / "hero.jpg")
    Image.new("RGBA", (32, 8), "#ffffff00").save(tmp_path / "logo.png")
    (tmp_path / "asset_manifest.json").write_text(
        json.dumps(
            {
                "assets": [
                    {"role": "logo", "path": "logo.svg", "preview_path": "logo.png"},
                    {"role": "hero", "path": "hero.jpg", "preview_path": None},
                ]
            }
        ),
        encoding="utf-8",
    )
    assert _asset_paths(tmp_path) == [(tmp_path / "hero.jpg").resolve()]


def test_metrics_never_claim_human_preference() -> None:
    class Match:
        relevance = .8
        category = 1.0
        format = 1.0
        diversity = .5

    class Metadata:
        source = "fixture"
        research_only = False

    class Result:
        match = Match()
        metadata = Metadata()
        reference_id = "fixture:one"
        template_family = "fixture:family"
        visual_text_score = .7

    metrics = _metrics([Result()])
    assert metrics["structural_relevance"] == .8
    assert metrics["retrieval_quality"] == .75
    assert "human_preference" not in metrics
