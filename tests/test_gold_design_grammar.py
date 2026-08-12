"""Unit tests for Gold Design Grammar contracts, library, extraction, adaptation, and pilot execution."""

from __future__ import annotations

from pathlib import Path
from training.evaluation.benchmark_briefs import BENCHMARK_BRIEFS
from training.evaluation.gold_grammar_pilot import run_gold_grammar_pilot
from training.gold.adapter import GoldDesignAdapter
from training.gold.extractor import GoldGrammarExtractor
from training.gold.library import get_gold_library, get_grammar_by_id, get_grammars_by_category
from training.schemas.design import BoundingBox, CanvasSpec, DesignDocument, DesignElement, NormalizedBoundingBox, SourceSpec, TextSpec, normalize_bbox
from training.schemas.gold import GoldDesignGrammarV1, GoldSlotV1


def test_gold_library_contains_15_provisional_grammars():
    library = get_gold_library()
    assert len(library) == 15
    for g in library:
        assert g.gold_status == "PROVISIONAL"
        assert g.provenance.get("commercial_allowed") is True
        assert len(g.slots) > 0

    categories = {"SPA", "CAFE", "SALE", "MENU", "SIGNAGE"}
    for cat in categories:
        cat_grammars = get_grammars_by_category(cat)
        assert len(cat_grammars) == 3


def test_gold_grammar_extractor():
    canvas = CanvasSpec(width=210, height=297, unit="mm")
    b1 = BoundingBox(x=20, y=240, width=170, height=30)
    b2 = BoundingBox(x=20, y=180, width=170, height=40)
    doc = DesignDocument(
        sample_id="sample_test_001",
        source=SourceSpec(
            name="test_source",
            split="benchmark",
            license_class="CC0_or_project_owned",
            upstream_id="upstream_001",
            commercial_allowed=True,
        ),
        canvas=canvas,
        category="SPA",
        elements=[
            DesignElement(
                id="brand_1",
                name="Brand Logo",
                type="text",
                bbox=b1,
                bbox_norm=normalize_bbox(b1, canvas),
                text=TextSpec(content="LUXURY SPA", font_family="Cambria", font_size=20, font_weight="bold"),
            ),
            DesignElement(
                id="headline_1",
                name="Main Headline",
                type="text",
                bbox=b2,
                bbox_norm=normalize_bbox(b2, canvas),
                text=TextSpec(content="SERENITY & WELLNESS", font_family="Cambria", font_size=28, font_weight="bold"),
            ),
        ],
    )

    extractor = GoldGrammarExtractor()
    grammar = extractor.extract(doc, grammar_id="gold_test_spa", grammar_name="Test Spa Grammar")

    assert grammar.grammar_id == "gold_test_spa"
    assert grammar.category == "SPA"
    assert grammar.gold_status == "PROVISIONAL"
    assert len(grammar.slots) == 2


def test_gold_design_adapter_business_content_immutability():
    grammar = get_grammar_by_id("gold_spa_001")
    adapter = GoldDesignAdapter()
    brief = BENCHMARK_BRIEFS[0]  # SPA brief

    doc, report = adapter.adapt(grammar, brief, candidate_index=0)

    assert doc.category == "SPA"
    assert len(doc.elements) > 0
    assert report["slot_fill_rate"] == 1.0
    assert report["grammar_deviation_score"] <= 0.1

    # Check business text immutability
    text_contents = [e.text.content for e in doc.elements if e.text]
    assert brief.business_name in text_contents or any(brief.business_name in t for t in text_contents)
    assert brief.headline in text_contents or any(brief.headline in t for t in text_contents)


def test_gold_grammar_pilot_execution(tmp_path: Path):
    metrics = run_gold_grammar_pilot(output_root=tmp_path, seed=42)

    assert metrics["status"] == "WAITING_FOR_GOLD_GRAMMAR_PILOT_HUMAN_REVIEW"
    assert metrics["total_gold_candidates"] == 20
    assert metrics["total_baseline_candidates"] == 5

    # Check files created
    assert (tmp_path / "manifest.json").exists()
    assert (tmp_path / "gold_grammar_pilot_contact_sheet.png").exists()
    assert (tmp_path / "baseline_vs_gold_contact_sheet.png").exists()
    assert (tmp_path / "comparisons" / "review_queue.jsonl").exists()
    assert (tmp_path / "comparisons" / "blind_mapping.json").exists()

    # Verify a candidate output directory
    cand_dir = tmp_path / "gold_candidates" / "spa" / "candidate_1"
    assert (cand_dir / "design.json").exists()
    assert (cand_dir / "gold_grammar.json").exists()
    assert (cand_dir / "adaptation_report.json").exists()
    assert (cand_dir / "corel_operations.json").exists()
    assert (cand_dir / "preview.png").exists()
    assert (cand_dir / "output.cdr").exists()
    assert (cand_dir / "metrics.json").exists()
    assert (cand_dir / "provenance.json").exists()
