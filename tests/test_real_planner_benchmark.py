"""Tests for the fail-closed real-planner shootout audit."""

from __future__ import annotations

from pathlib import Path

from training.evaluation.benchmark_briefs import get_brief_by_id
from training.evaluation.real_planner_audit import (
    _audit_antigravity_result,
    _audit_qwen_result,
    perform_real_planner_audit,
    run_real_planner_pilot,
)
from training.inference.planners import (
    FixtureAntigravityPlanner,
    FixtureQwenPlanner,
    RealAntigravityDesignPlanner,
    RealQwenDesignPlanner,
)


def test_fixture_planners_are_explicit_fixtures() -> None:
    brief = get_brief_by_id("brief_sale_01")

    qwen = FixtureQwenPlanner().plan(brief, candidate_index=0)
    assert qwen.planner_type == "fixture"
    assert qwen.metadata.get("fixture_mode") is True
    assert qwen.raw_output == ""

    antigravity = FixtureAntigravityPlanner().plan(brief, candidate_index=0)
    assert antigravity.planner_type == "fixture"
    assert antigravity.metadata.get("fixture_mode") is True
    assert antigravity.raw_output == ""


def test_audit_is_frozen_by_default_and_does_not_execute_models() -> None:
    report = perform_real_planner_audit()
    assert report["schema_version"] == "2.0"
    assert report["conclusion"] == "PLANNER_SHOOTOUT_FROZEN"
    assert report["benchmark_valid"] is False
    assert report["execution_performed"] is False
    assert report["qwen"]["status"] == "NOT_EXECUTED"
    assert report["antigravity"]["status"] == "NOT_EXECUTED"


def test_current_qwen_wrapper_cannot_pass_ai_derivation_gate_when_forced_off() -> None:
    brief = get_brief_by_id("brief_spa_01")
    result = RealQwenDesignPlanner(force_fake=True).plan(brief, candidate_index=0)
    audit = _audit_qwen_result(result, brief)

    assert audit["real_model_invoked"] is False
    assert audit["design_plan_derived_from_ai_output"] is False
    assert audit["valid"] is False


def test_current_antigravity_wrapper_cannot_pass_external_execution_gate() -> None:
    brief = get_brief_by_id("brief_spa_01")
    result = RealAntigravityDesignPlanner(mode="mode_a_text").plan(brief, candidate_index=0)
    audit = _audit_antigravity_result(result, brief)

    # The historical class can construct a synthetic response, but it does not
    # prove an external Antigravity invocation or an AI-derived DesignPlanV2.
    assert audit["external_execution_verified"] is False
    assert audit["design_plan_derived_from_ai_output"] is False
    assert audit["valid"] is False


def test_frozen_pilot_generates_no_candidates_review_queue_or_fake_cdr(tmp_path: Path) -> None:
    output_root = tmp_path / "planner_shootout"
    result = run_real_planner_pilot(output_root=output_root)

    assert result["status"] == "PLANNER_SHOOTOUT_FROZEN"
    assert result["benchmark_valid"] is False
    assert result["pilot_generated"] is False
    assert result["total_pilot_candidates"] == 0
    assert result["pilot_pairs"] == 0
    assert result["human_review_ready"] is False
    assert result["review_queue_created"] is False
    assert result["real_cdr_verified"] is False
    assert result["commercial_allowed"] is False

    assert (output_root / "REAL_PLANNER_AUDIT.json").exists()
    assert not (output_root / "comparisons" / "review_queue.jsonl").exists()
    assert list(output_root.rglob("*.cdr")) == []
