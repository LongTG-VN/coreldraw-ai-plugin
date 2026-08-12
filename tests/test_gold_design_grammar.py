"""Unit tests for Gold grammar contracts, extraction, adaptation, and fixture pilot."""

from __future__ import annotations

import json
from pathlib import Path

from training.evaluation.benchmark_briefs import BENCHMARK_BRIEFS
from training.evaluation.gold_grammar_pilot import run_gold_grammar_pilot
from training.gold.adapter import GoldDesignAdapter
from training.gold.extractor import GoldGrammarExtractor
from training.gold.library import get_gold_library, get_grammar_by_id, get_grammars_by_category
from training.schemas.design import (
    BoundingBox,
    CanvasSpec,
    DesignDocument,
    DesignElement,
    SourceSpec,
    TextSpec,
    normalize_bbox,
)


def test_manual_grammar_library_is_fail_closed():
    library = get_gold_library()
    assert len(library) == 15
    for grammar in library:
        assert grammar.gold_status == "PROVISIONAL"
        assert grammar.provenance.get("commercial_allowed") is False
        assert grammar.provenance.get("project_owned") is False
        assert grammar.provenance.get("license_class") == "UNKNOWN"
        assert len(grammar.slots) > 0

    for category in {"SPA", "CAFE", "SALE", "MENU", "SIGNAGE"}:
        assert len(get_grammars_by_category(category)) == 3


def test_gold_grammar_extractor_inherits_source_rights():
    canvas = CanvasSpec(width=210, height=297, unit="mm")
    brand_box = BoundingBox(x=20, y=240, width=170, height=30)
    headline_box = BoundingBox(x=20, y=180, width=170, height=40)
    document = DesignDocument(
        sample_id="sample_test_001",
        source=SourceSpec(
            name="test_source",
            split="benchmark",
            license_class="TEST-LICENSE",
            upstream_id="upstream_001",
            commercial_allowed=False,
        ),
        canvas=canvas,
        category="SPA",
        elements=[
            DesignElement(
                id="brand_1",
                name="Brand Name",
                type="text",
                bbox=brand_box,
                bbox_norm=normalize_bbox(brand_box, canvas),
                text=TextSpec(
                    content="LUXURY SPA",
                    font_family="Cambria",
                    font_size=20,
                    font_weight="bold",
                ),
            ),
            DesignElement(
                id="headline_1",
                name="Main Headline",
                type="text",
                bbox=headline_box,
                bbox_norm=normalize_bbox(headline_box, canvas),
                text=TextSpec(
                    content="SERENITY & WELLNESS",
                    font_family="Cambria",
                    font_size=28,
                    font_weight="bold",
                ),
            ),
        ],
    )

    grammar = GoldGrammarExtractor().extract(
        document,
        grammar_id="gold_test_spa",
        grammar_name="Test Spa Grammar",
    )

    assert grammar.grammar_id == "gold_test_spa"
    assert grammar.category == "SPA"
    assert grammar.gold_status == "PROVISIONAL"
    assert len(grammar.slots) == 2
    assert grammar.provenance["license_class"] == "TEST-LICENSE"
    assert grammar.provenance["commercial_allowed"] is False
    assert grammar.provenance["source_upstream_id"] == "upstream_001"


def test_gold_design_adapter_preserves_business_content_and_rights():
    grammar = get_grammar_by_id("gold_spa_001")
    adapter = GoldDesignAdapter()
    brief = BENCHMARK_BRIEFS[0]

    document, report = adapter.adapt(grammar, brief, candidate_index=0)

    assert document.category == "SPA"
    assert len(document.elements) > 0
    assert report["slot_fill_rate"] > 0
    assert report["grammar_deviation_score"] == 0.0
    assert document.source.commercial_allowed is False
    assert document.source.license_class == "UNKNOWN"

    text_contents = [element.text.content for element in document.elements if element.text]
    assert any(brief.business_name in text for text in text_contents)
    assert any(brief.headline in text for text in text_contents)


def test_manual_grammar_pilot_is_regression_only_and_never_writes_cdr(tmp_path: Path):
    metrics = run_gold_grammar_pilot(output_root=tmp_path, seed=42)

    assert metrics["status"] == "STRUCTURED_GRAMMAR_ADAPTATION_PILOT_ONLY"
    assert metrics["benchmark_validity"] == "REGRESSION_FIXTURE_ONLY"
    assert metrics["total_gold_candidates"] == 20
    assert metrics["total_baseline_candidates"] == 5
    assert metrics["real_gold_reference_count"] == 0
    assert metrics["baseline_type"] == "fixture"
    assert metrics["human_review_ready"] is False
    assert metrics["human_comparison_queue_created"] is False
    assert metrics["real_cdr_verified"] is False
    assert metrics["commercial_allowed"] is False

    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["manual_grammars"] is True
    assert manifest["human_review_ready"] is False

    assert (tmp_path / "gold_grammar_pilot_contact_sheet.png").exists()
    assert (tmp_path / "baseline_vs_gold_contact_sheet.png").exists()
    assert not (tmp_path / "comparisons" / "review_queue.jsonl").exists()

    candidate_dir = tmp_path / "gold_candidates" / "spa" / "candidate_1"
    assert (candidate_dir / "design.json").exists()
    assert (candidate_dir / "gold_grammar.json").exists()
    assert (candidate_dir / "adaptation_report.json").exists()
    assert (candidate_dir / "corel_operations.json").exists()
    assert (candidate_dir / "preview.png").exists()
    assert (candidate_dir / "cdr_request.json").exists()
    assert not (candidate_dir / "output.cdr").exists()

    provenance = json.loads((candidate_dir / "provenance.json").read_text(encoding="utf-8"))
    assert provenance["grammar_origin"] == "MANUALLY_AUTHORED_GRAMMAR"
    assert provenance["commercial_allowed"] is False
    assert provenance["real_gold_reference"] is False
    assert provenance["real_cdr_verified"] is False
