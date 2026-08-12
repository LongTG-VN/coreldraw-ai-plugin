"""Hermetic tests for the stabilized real-reference Gold research pipeline."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from training.evaluation.real_gold_pilot import run_real_gold_grammar_pilot
from training.gold.real_pipeline import (
    GENPOSTER_LICENSE_CLASS,
    GoldSourceApprovalRequired,
    build_real_gold_library,
    discover_source_candidates,
    load_real_sources_from_dataset,
)


def _dataset_entry(sample_id: str, index: int) -> dict:
    shift = index * 2
    return {
        "sample_id": sample_id,
        "canvas": {"width": 1000, "height": 1400},
        "elements": [
            {
                "name": "background",
                "type": "rectangle",
                "bbox": {"x": 20, "y": 20, "width": 960, "height": 1360},
                "z_index": 0,
            },
            {
                "name": "headline",
                "type": "text",
                "bbox": {"x": 100 + shift, "y": 120, "width": 700, "height": 180},
                "text": {
                    "content": f"SOURCE HEADLINE {sample_id}",
                    "font_family": "Arial Bold",
                    "font_size": 64,
                    "alignment": "left",
                },
                "z_index": 2,
            },
            {
                "name": "body text",
                "type": "text",
                "bbox": {"x": 100, "y": 360 + shift, "width": 650, "height": 180},
                "text": {
                    "content": f"Source body {sample_id}",
                    "font_family": "Arial",
                    "font_size": 28,
                    "alignment": "left",
                },
                "z_index": 2,
            },
            {
                "name": "price offer",
                "type": "text",
                "bbox": {"x": 100, "y": 600, "width": 350, "height": 120},
                "text": {
                    "content": "SOURCE OFFER 99",
                    "font_family": "Arial Bold",
                    "font_size": 42,
                    "alignment": "left",
                },
                "z_index": 3,
            },
            {
                "name": "cta button",
                "type": "text",
                "bbox": {"x": 100, "y": 780, "width": 300, "height": 100},
                "text": {
                    "content": "SOURCE CTA",
                    "font_family": "Arial Bold",
                    "font_size": 30,
                    "alignment": "center",
                },
                "z_index": 3,
            },
        ],
    }


def _write_dataset_and_manifest(tmp_path: Path) -> tuple[Path, Path]:
    dataset = tmp_path / "train.jsonl"
    entries = []
    approved = []
    for category in ("SALE", "SPA"):
        for index in range(3):
            upstream_id = f"{category.lower()}_upstream_{index + 1}"
            source_id = f"approved_{category.lower()}_{index + 1:03d}"
            entries.append(_dataset_entry(upstream_id, index))
            approved.append(
                {
                    "source_id": source_id,
                    "upstream_id": upstream_id,
                    "category": category,
                    "approved": True,
                    "human_quality_status": "APPROVED",
                    "review_notes": "test fixture only",
                }
            )
    dataset.write_text(
        "".join(json.dumps(entry) + "\n" for entry in entries), encoding="utf-8"
    )
    manifest = tmp_path / "approved.json"
    manifest.write_text(json.dumps({"sources": approved}, indent=2), encoding="utf-8")
    return dataset, manifest


def test_discovery_is_neutral_and_does_not_auto_approve(tmp_path: Path):
    dataset, _ = _write_dataset_and_manifest(tmp_path)
    rows = discover_source_candidates(dataset, limit=2)
    assert len(rows) == 2
    assert all(row["approved"] is False for row in rows)
    assert all(row["human_quality_status"] == "UNREVIEWED" for row in rows)
    assert all("category" not in row for row in rows)


def test_missing_approval_manifest_fails_closed(tmp_path: Path):
    dataset, _ = _write_dataset_and_manifest(tmp_path)
    with pytest.raises(GoldSourceApprovalRequired):
        load_real_sources_from_dataset(dataset, tmp_path / "missing.json")


def test_unapproved_manifest_row_is_rejected(tmp_path: Path):
    dataset, manifest = _write_dataset_and_manifest(tmp_path)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["sources"][0]["approved"] = False
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(GoldSourceApprovalRequired):
        load_real_sources_from_dataset(dataset, manifest)


def test_build_real_gold_library_binds_research_only_rights(tmp_path: Path):
    dataset, manifest = _write_dataset_and_manifest(tmp_path)
    output = tmp_path / "gold"
    grammars, inventory = build_real_gold_library(
        output_dir=output,
        dataset_path=dataset,
        approved_manifest_path=manifest,
    )

    assert len(grammars) == 6
    assert inventory["total_sources"] == 6
    assert inventory["sale_source_count"] == 3
    assert inventory["spa_source_count"] == 3
    assert inventory["commercial_allowed"] is False

    for grammar in grammars:
        assert grammar.gold_status == "PROVISIONAL_REAL_REFERENCE"
        assert grammar.provenance["extracted_from_real_design"] is True
        assert grammar.provenance["human_approved"] is True
        assert grammar.provenance["license_class"] == GENPOSTER_LICENSE_CLASS
        assert grammar.provenance["commercial_allowed"] is False
        assert grammar.provenance["project_owned"] is False

    sample_dir = output / "sale" / "approved_sale_001"
    assert (sample_dir / "source_entry.json").exists()
    assert (sample_dir / "source_manifest.json").exists()
    assert (sample_dir / "source_preview.png").exists()
    assert (sample_dir / "grammar.json").exists()
    assert (sample_dir / "extraction_report.json").exists()


def test_stabilized_pilot_never_writes_fake_cdr(tmp_path: Path):
    dataset, manifest = _write_dataset_and_manifest(tmp_path)
    output = tmp_path / "pilot"
    metrics = run_real_gold_grammar_pilot(
        output_root=output,
        seed=42,
        dataset_path=dataset,
        approved_manifest_path=manifest,
    )

    assert metrics["status"] == "STABILIZED_RESEARCH_PILOT_READY"
    assert metrics["conclusion"] == "REAL_REFERENCE_STRUCTURE_PROVENANCE_VERIFIED"
    assert metrics["pilot_generated"] is True
    assert metrics["total_real_gold_candidates"] == 8
    assert metrics["total_baseline_candidates"] == 0
    assert metrics["real_cdr_verified"] is False
    assert metrics["cdr_export_required"] is True
    assert metrics["commercial_allowed"] is False
    assert metrics["human_comparison_queue_created"] is False

    candidate_dir = output / "real_gold_candidates" / "sale" / "candidate_1"
    assert (candidate_dir / "design.json").exists()
    assert (candidate_dir / "grammar.json").exists()
    assert (candidate_dir / "source_reference.json").exists()
    assert (candidate_dir / "adaptation_report.json").exists()
    assert (candidate_dir / "corel_operations.json").exists()
    assert (candidate_dir / "preview.png").exists()
    assert (candidate_dir / "cdr_request.json").exists()
    assert not (candidate_dir / "output.cdr").exists()

    provenance = json.loads((candidate_dir / "provenance.json").read_text(encoding="utf-8"))
    assert provenance["commercial_allowed"] is False
    assert provenance["project_owned"] is False
    assert provenance["real_cdr_verified"] is False


def test_pilot_blocks_before_generation_without_human_approval(tmp_path: Path):
    dataset, _ = _write_dataset_and_manifest(tmp_path)
    metrics = run_real_gold_grammar_pilot(
        output_root=tmp_path / "pilot",
        dataset_path=dataset,
        approved_manifest_path=tmp_path / "missing.json",
    )
    assert metrics["status"] == "WAITING_FOR_SOURCE_HUMAN_APPROVAL"
    assert metrics["pilot_generated"] is False
    assert metrics["commercial_allowed"] is False
