"""Tests for Real AI Planners, Audit Gate, and Pilot Benchmark infrastructure."""

from __future__ import annotations

import json
from pathlib import Path

from training.evaluation.benchmark_briefs import get_brief_by_id
from training.evaluation.real_planner_audit import (
    perform_real_planner_audit,
    run_real_planner_pilot,
)
from training.inference.planner_base import validate_content_lock
from training.inference.planners import (
    FixtureAntigravityPlanner,
    FixtureQwenPlanner,
    RealAntigravityDesignPlanner,
    RealQwenDesignPlanner,
)


def test_fixture_planners_provenance() -> None:
    brief = get_brief_by_id("brief_sale_01")
    fq_planner = FixtureQwenPlanner()
    res_q = fq_planner.plan(brief, candidate_index=0)

    assert res_q.planner_name == "Qwen3-1.7B"
    assert res_q.planner_type == "fixture"
    assert res_q.metadata.get("fixture_mode") is True
    assert res_q.raw_output == ""

    fa_planner = FixtureAntigravityPlanner()
    res_a = fa_planner.plan(brief, candidate_index=0)

    assert res_a.planner_name == "Antigravity"
    assert res_a.planner_type == "fixture"
    assert res_a.metadata.get("fixture_mode") is True
    assert res_a.raw_output == ""



def test_real_antigravity_planner_raw_output() -> None:
    brief = get_brief_by_id("brief_spa_01")
    ag_planner = RealAntigravityDesignPlanner(mode="mode_a_text")
    res = ag_planner.plan(brief, candidate_index=0)

    assert res.planner_name == "RealAntigravity"
    assert res.planner_type == "agent_reasoning"
    assert res.raw_output != ""
    assert "antigravity_reasoning_trace" in res.raw_output
    assert res.latency_seconds > 0.0
    assert res.started_at != ""
    assert res.completed_at != ""
    assert validate_content_lock(res.document, brief) is True


def test_real_qwen_planner_raw_output() -> None:
    brief = get_brief_by_id("brief_spa_01")
    qwen_planner = RealQwenDesignPlanner()
    res = qwen_planner.plan(brief, candidate_index=0)

    assert res.planner_name == "RealQwen3-1.7B"
    assert res.planner_type == "neural_llm"
    if res.metadata.get("real_model_invoked"):
        assert res.raw_output != ""
        assert res.latency_seconds > 0.0
    assert res.request_prompt != ""
    assert validate_content_lock(res.document, brief) is True


def test_audit_gate_evaluation() -> None:
    audit_report = perform_real_planner_audit()

    assert audit_report["schema_version"] == "1.0"
    assert "conclusion" in audit_report


def test_run_real_planner_pilot_end_to_end(tmp_path: Path) -> None:
    output_root = tmp_path / "test_real_pilot"
    pilot_res = run_real_planner_pilot(output_root=output_root, mode="mode_a_text")

    assert "status" in pilot_res
    assert "conclusion" in pilot_res
    if pilot_res.get("pilot_generated"):
        assert pilot_res["total_pilot_candidates"] == 8
        assert pilot_res["pilot_pairs"] == 4
        queue_file = output_root / "comparisons" / "review_queue.jsonl"
        assert queue_file.exists()
        lines = queue_file.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 4

        qwen_cand_dir = output_root / "mode_a_text" / "qwen" / "brief_sale_01" / "candidate_1"
        assert (qwen_cand_dir / "planner_request.json").exists()
        assert (qwen_cand_dir / "raw_planner_output.txt").exists()
        assert (qwen_cand_dir / "design_plan.json").exists()
        assert (qwen_cand_dir / "design.json").exists()
        assert (qwen_cand_dir / "corel_operations.json").exists()
        assert (qwen_cand_dir / "preview.png").exists()
        assert (qwen_cand_dir / "output.cdr").exists()
        assert (qwen_cand_dir / "metrics.json").exists()
        assert (qwen_cand_dir / "provenance.json").exists()

        raw_out = (qwen_cand_dir / "raw_planner_output.txt").read_text(encoding="utf-8")
        assert len(raw_out.strip()) > 0

    audit_file = output_root / "REAL_PLANNER_AUDIT.json"
    assert audit_file.exists()
