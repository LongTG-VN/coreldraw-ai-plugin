"""Tests for the Antigravity vs Qwen planner shootout benchmark infrastructure."""

from __future__ import annotations

import json
from pathlib import Path

from training.evaluation.benchmark_briefs import BENCHMARK_BRIEFS, get_brief_by_id
from training.evaluation.planner_shootout import run_planner_shootout
from training.inference.planner_base import (
    ContentLockSpec,
    DesignPlanV2,
    validate_content_lock,
)
from training.inference.planners import AntigravityDesignPlanner, QwenDesignPlanner


def test_benchmark_briefs_count_and_content() -> None:
    assert len(BENCHMARK_BRIEFS) == 5
    categories = {brief.category for brief in BENCHMARK_BRIEFS}
    assert categories == {"SPA", "CAFE", "SALE", "MENU", "SIGNAGE"}

    spa_brief = get_brief_by_id("brief_spa_01")
    assert spa_brief.business_name == "SERENE SPA & WELLNESS"
    assert spa_brief.canvas_width_mm == 210.0
    assert spa_brief.canvas_height_mm == 297.0


def test_content_lock_hashing_and_validation() -> None:
    brief = get_brief_by_id("brief_sale_01")
    c_hash = brief.compute_content_hash()
    a_hash = brief.compute_asset_hash()
    canvas_hash = brief.compute_canvas_hash()

    assert len(c_hash) == 64
    assert len(a_hash) == 64
    assert len(canvas_hash) == 64

    ag_planner = AntigravityDesignPlanner()
    res = ag_planner.plan(brief, candidate_index=0)

    assert res.planner_name == "Antigravity"
    assert res.layout_family == "luxury_editorial"
    assert validate_content_lock(res.document, brief) is True


def test_qwen_planner_contract() -> None:
    brief = get_brief_by_id("brief_cafe_01")
    qwen_planner = QwenDesignPlanner()
    res = qwen_planner.plan(brief, candidate_index=1)

    assert res.planner_name == "Qwen3-1.7B"
    assert res.layout_family == "asymmetric_left"
    assert len(res.document.elements) >= 4
    assert validate_content_lock(res.document, brief) is True


def test_run_planner_shootout_end_to_end(tmp_path: Path) -> None:
    output_root = tmp_path / "test_shootout"
    metrics = run_planner_shootout(output_root=output_root, seed=123)

    assert metrics["total_candidates"] == 40
    assert metrics["qwen_candidate_count"] == 20
    assert metrics["antigravity_candidate_count"] == 20
    assert metrics["qwen_technical_pass_rate"] == 1.0
    assert metrics["antigravity_technical_pass_rate"] == 1.0
    assert metrics["pairs_generated"] == 20
    assert metrics["status"] == "WAITING_FOR_BLIND_HUMAN_REVIEW"

    # Verify manifest file
    manifest_file = output_root / "manifest.json"
    assert manifest_file.exists()
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    assert manifest["total_target_candidates"] == 40

    # Verify review queue file
    queue_file = output_root / "blind_review" / "review_queue.jsonl"
    assert queue_file.exists()
    lines = queue_file.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 20

    # Verify contact sheets
    hidden_sheet = output_root / "blind_review" / "planner_candidates_hidden_contact_sheet.png"
    unblinded_sheet = output_root / "blind_review" / "planner_candidates_unblinded_audit.png"
    assert hidden_sheet.exists()
    assert unblinded_sheet.exists()
