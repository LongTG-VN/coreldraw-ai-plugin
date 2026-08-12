"""Unit tests for Phase 1.3b Real Reference Gold Design Grammar pipeline and provenance audit."""

from __future__ import annotations

from pathlib import Path

from training.evaluation.real_gold_pilot import run_real_gold_grammar_pilot
from training.gold.real_pipeline import build_real_gold_library, load_real_sources_from_dataset


def test_load_real_sources_from_dataset():
    sources = load_real_sources_from_dataset()
    assert "SALE" in sources
    assert "SPA" in sources
    assert len(sources["SALE"]) == 5
    assert len(sources["SPA"]) == 5


def test_build_real_gold_library(tmp_path: Path):
    real_grammars, inventory = build_real_gold_library(output_dir=tmp_path)

    assert len(real_grammars) == 10
    assert inventory["total_sources"] == 10
    assert inventory["sale_source_count"] == 5
    assert inventory["spa_source_count"] == 5

    for g in real_grammars:
        assert g.gold_status == "PROVISIONAL_REAL_REFERENCE"
        assert g.provenance["extracted_from_real_design"] is True
        assert bool(g.provenance["source_sha256"]) is True

    # Check evidence files created
    sale_sample_dir = tmp_path / "sale" / "real_sale_001"
    assert (sale_sample_dir / "grammar.json").exists()
    assert (sale_sample_dir / "source_manifest.json").exists()
    assert (sale_sample_dir / "source_preview.png").exists()
    assert (sale_sample_dir / "extraction_report.json").exists()


def test_real_gold_grammar_pilot_execution(tmp_path: Path):
    metrics = run_real_gold_grammar_pilot(output_root=tmp_path, seed=42)

    assert metrics["status"] == "WAITING_FOR_REAL_GOLD_ADAPTATION_HUMAN_REVIEW"
    assert metrics["conclusion"] == "REAL_GOLD_PIPELINE_VERIFIED"
    assert metrics["pilot_generated"] is True
    assert metrics["total_real_gold_candidates"] == 8
    assert metrics["total_baseline_candidates"] == 2

    # Check files created
    assert (tmp_path / "real_gold_source_contact_sheet.png").exists()
    assert (tmp_path / "real_gold_adaptation_contact_sheet.png").exists()
    assert (tmp_path / "baseline_vs_real_gold.png").exists()
    assert (tmp_path / "REAL_GOLD_PROVENANCE_AUDIT.json").exists()
    assert (tmp_path / "comparisons" / "review_queue.jsonl").exists()

    # Check candidate directory
    cand_dir = tmp_path / "real_gold_candidates" / "sale" / "candidate_1"
    assert (cand_dir / "design.json").exists()
    assert (cand_dir / "grammar.json").exists()
    assert (cand_dir / "source_reference.json").exists()
    assert (cand_dir / "adaptation_report.json").exists()
    assert (cand_dir / "corel_operations.json").exists()
    assert (cand_dir / "preview.png").exists()
    assert (cand_dir / "output.cdr").exists()
    assert (cand_dir / "metrics.json").exists()
    assert (cand_dir / "provenance.json").exists()
