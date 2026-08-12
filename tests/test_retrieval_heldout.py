from __future__ import annotations

from training.evaluation.retrieval_heldout import (
    RetrievalBenchmarkCase,
    evaluate_retrieval_heldout,
    evaluate_retrieval_mode,
)
from training.retrieval import (
    ReferenceMetadataV1,
    ReferenceRecordV1,
    extract_reference_features,
    summarize_reference,
)
from training.tools.build_reference_corpus import _generic_document


def _record(category: str, variant: str, source: str) -> ReferenceRecordV1:
    document = _generic_document(
        category if category != "poster" else "spa",
        variant,
        ["cream", "gold"],
    )
    features = extract_reference_features(document)
    reference_id = f"{source}:{category}:{variant}"
    metadata = ReferenceMetadataV1(
        reference_id=reference_id,
        category=category,
        format="poster" if category == "poster" else str(document.metadata["format"]),
        aspect_ratio=float(features.aspect_ratio),
        style_tags=["minimal", variant],
        color_tags=["cream", "gold"],
        text_density=features.text_density,
        element_count=features.element_count,
        layout_features={"composition": features.composition},
        design_document_path=f"documents/{reference_id}.json",
        preview_path=f"previews/{reference_id}.png",
        source=source,
        license="CC-BY-NC-4.0" if source == "genposter100k" else "project_owned",
        license_class="research_only" if source == "genposter100k" else "production_safe",
        research_only=source == "genposter100k",
        commercial_allowed=source != "genposter100k",
    )
    return ReferenceRecordV1(
        metadata=metadata,
        features=features,
        summary=summarize_reference(metadata, features),
    )


class Provider:
    provider_name = "fixture"

    def __init__(self) -> None:
        self.records = [
            _record("spa", "hero_right", "synthetic_owned"),
            _record("spa", "centered", "synthetic_owned"),
            _record("poster", "split", "genposter100k"),
            _record("poster", "grid", "genposter100k"),
        ]

    def load_references(self) -> list[ReferenceRecordV1]:
        return list(self.records)


CASE = RetrievalBenchmarkCase(
    prompt_id="spa",
    prompt="Poster spa cao cấp màu kem vàng",
    width=210,
    height=297,
    expected_category="spa",
    expected_format="poster",
)


def test_heldout_mode_removes_exact_category_owned_templates() -> None:
    full = evaluate_retrieval_mode(Provider(), [CASE], mode="full_corpus", top_k=2)
    held = evaluate_retrieval_mode(
        Provider(),
        [CASE],
        mode="exclude_exact_category_owned_templates",
        top_k=2,
    )

    assert full["category_accuracy"] == 1
    assert full["fallback_rate"] == 0
    assert held["category_accuracy"] == 0
    assert held["format_accuracy"] == 1
    assert held["fallback_rate"] == 1
    assert held["rows"][0]["sources"] == ["genposter100k"]


def test_three_mode_report_is_deterministic_and_does_not_claim_aesthetics() -> None:
    first = evaluate_retrieval_heldout(Provider(), [CASE], top_k=2)
    second = evaluate_retrieval_heldout(Provider(), [CASE], top_k=2)

    assert first == second
    assert set(first["modes"]) == {
        "full_corpus",
        "exclude_exact_category_owned_templates",
        "genposter_only",
    }
    assert first["human_aesthetic_judgment"] is False
    assert first["modes"]["genposter_only"]["category_accuracy"] == 0
