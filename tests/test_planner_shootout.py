"""Tests for the quarantined deterministic planner-adapter framework smoke."""

from __future__ import annotations

import json
from pathlib import Path

from training.evaluation.benchmark_briefs import BENCHMARK_BRIEFS, get_brief_by_id
from training.evaluation.planner_shootout import run_planner_shootout
from training.inference.planner_base import validate_content_lock
from training.inference.planners import FixtureAntigravityPlanner, FixtureQwenPlanner


def test_benchmark_briefs_count_and_content() -> None:
    assert len(BENCHMARK_BRIEFS) == 5
    assert {brief.category for brief in BENCHMARK_BRIEFS} == {"SPA", "CAFE", "SALE", "MENU", "SIGNAGE"}

    spa = get_brief_by_id("brief_spa_01")
    assert spa.business_name == "SERENE SPA & WELLNESS"
    assert spa.canvas_width_mm == 210.0
    assert spa.canvas_height_mm == 297.0


def test_fixture_planners_are_content_lock_smoke_only() -> None:
    brief = get_brief_by_id("brief_sale_01")

    antigravity = FixtureAntigravityPlanner().plan(brief, candidate_index=0)
    assert antigravity.planner_type == "fixture"
    assert antigravity.layout_family == "luxury_editorial"
    assert validate_content_lock(antigravity.document, brief) is True

    qwen = FixtureQwenPlanner().plan(brief, candidate_index=1)
    assert qwen.planner_type == "fixture"
    assert qwen.layout_family == "asymmetric_left"
    assert validate_content_lock(qwen.document, brief) is True


def test_run_planner_shootout_is_fixture_framework_smoke_only(tmp_path: Path) -> None:
    output_root = tmp_path / "test_shootout"
    metrics = run_planner_shootout(output_root=output_root, seed=123)

    assert metrics["status"] == "DETERMINISTIC_ADAPTER_FRAMEWORK_SMOKE"
    assert metrics["benchmark_validity"] == "NOT_VALID_FOR_AI_PLANNER_COMPARISON"
    assert metrics["total_candidates"] == 40
    assert metrics["qwen_candidate_count"] == 20
    assert metrics["antigravity_candidate_count"] == 20
    assert metrics["qwen_technical_pass_rate"] == 1.0
    assert metrics["antigravity_technical_pass_rate"] == 1.0
    assert metrics["pairs_generated"] == 0
    assert metrics["human_review_ready"] is False
    assert metrics["review_queue_created"] is False
    assert metrics["real_cdr_verified"] is False
    assert metrics["commercial_allowed"] is False

    manifest = json.loads((output_root / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["benchmark_validity"] == "DETERMINISTIC_ADAPTER_FRAMEWORK_SMOKE"
    assert manifest["valid_for_ai_planner_comparison"] is False
    assert manifest["planners_are_fixtures"] is True
    assert manifest["human_review_ready"] is False

    assert not (output_root / "blind_review" / "review_queue.jsonl").exists()
    assert (output_root / "framework_audit" / "deterministic_adapter_contact_sheet.png").exists()
    assert list(output_root.rglob("*.cdr")) == []

    candidate_dir = output_root / "qwen_fixture" / "brief_spa_01" / "candidate_1"
    assert (candidate_dir / "design.json").exists()
    assert (candidate_dir / "planner_output.json").exists()
    assert (candidate_dir / "corel_operations.json").exists()
    assert (candidate_dir / "preview.png").exists()
    assert (candidate_dir / "cdr_request.json").exists()

    provenance = json.loads((candidate_dir / "provenance.json").read_text(encoding="utf-8"))
    assert provenance["planner_type"] == "fixture"
    assert provenance["ai_planner_invoked"] is False
    assert provenance["commercial_allowed"] is False
    assert provenance["real_cdr_verified"] is False
