"""Fail-closed audit for the quarantined Antigravity vs Qwen planner shootout.

Historical implementations used fixture-derived structured plans while reporting
"real" planner activity. This module intentionally refuses to generate a pilot or
human-review queue until each planner can prove that its ``DesignPlanV2`` derives
from a fresh external/model output.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from training.evaluation.benchmark_briefs import get_brief_by_id
from training.inference.planner_base import (
    ContentLockSpec,
    PlannerGenerationResult,
    validate_content_lock,
)
from training.inference.planners import RealAntigravityDesignPlanner, RealQwenDesignPlanner


REAL_BENCHMARK_ROOT = Path(
    "training/artifacts/benchmarks/20260812_real_antigravity_vs_qwen_planner"
)


REQUIRED_QWEN_PROVENANCE_FLAGS = (
    "real_model_invoked",
    "design_plan_derived_from_ai_output",
)
REQUIRED_ANTIGRAVITY_PROVENANCE_FLAGS = (
    "real_agent_planning",
    "external_execution_verified",
    "design_plan_derived_from_ai_output",
)


def _audit_qwen_result(
    result: PlannerGenerationResult,
    brief: ContentLockSpec,
) -> dict[str, Any]:
    metadata = result.metadata
    raw_non_empty = bool(result.raw_output and result.raw_output.strip())
    prompt_exists = bool(result.request_prompt and result.request_prompt.strip())
    real_model_invoked = metadata.get("real_model_invoked") is True
    plan_derived = metadata.get("design_plan_derived_from_ai_output") is True
    fallback_used = metadata.get("fallback_used") is True or metadata.get("fixture_mode") is True
    content_lock_valid = validate_content_lock(result.document, brief)
    latency_valid = result.latency_seconds > 0.0

    valid = all(
        (
            result.planner_type == "neural_llm",
            real_model_invoked,
            raw_non_empty,
            prompt_exists,
            plan_derived,
            not fallback_used,
            content_lock_valid,
            latency_valid,
        )
    )
    return {
        "planner_name": result.planner_name,
        "planner_type": result.planner_type,
        "real_model_invoked": real_model_invoked,
        "raw_output_non_empty": raw_non_empty,
        "real_prompt_exists": prompt_exists,
        "design_plan_derived_from_ai_output": plan_derived,
        "fallback_used": fallback_used,
        "content_lock_valid": content_lock_valid,
        "real_latency_recorded": latency_valid,
        "latency_seconds": result.latency_seconds,
        "required_provenance_flags": list(REQUIRED_QWEN_PROVENANCE_FLAGS),
        "valid": valid,
    }


def _audit_antigravity_result(
    result: PlannerGenerationResult,
    brief: ContentLockSpec,
) -> dict[str, Any]:
    metadata = result.metadata
    raw_non_empty = bool(result.raw_output and result.raw_output.strip())
    prompt_exists = bool(result.request_prompt and result.request_prompt.strip())
    real_agent_planning = metadata.get("real_agent_planning") is True
    external_execution_verified = metadata.get("external_execution_verified") is True
    plan_derived = metadata.get("design_plan_derived_from_ai_output") is True
    synthetic_trace = metadata.get("synthetic_reasoning_trace") is True
    fallback_used = metadata.get("fallback_used") is True or metadata.get("fixture_mode") is True
    content_lock_valid = validate_content_lock(result.document, brief)
    latency_valid = result.latency_seconds > 0.0

    valid = all(
        (
            result.planner_type == "agent_reasoning",
            real_agent_planning,
            external_execution_verified,
            raw_non_empty,
            prompt_exists,
            plan_derived,
            not synthetic_trace,
            not fallback_used,
            content_lock_valid,
            latency_valid,
        )
    )
    return {
        "planner_name": result.planner_name,
        "planner_type": result.planner_type,
        "real_agent_planning": real_agent_planning,
        "external_execution_verified": external_execution_verified,
        "raw_output_non_empty": raw_non_empty,
        "real_planner_input_exists": prompt_exists,
        "design_plan_derived_from_ai_output": plan_derived,
        "synthetic_reasoning_trace": synthetic_trace,
        "fallback_used": fallback_used,
        "content_lock_valid": content_lock_valid,
        "real_elapsed_time_recorded": latency_valid,
        "latency_seconds": result.latency_seconds,
        "required_provenance_flags": list(REQUIRED_ANTIGRAVITY_PROVENANCE_FLAGS),
        "valid": valid,
    }


def _conclusion(qwen_valid: bool, antigravity_valid: bool) -> str:
    if qwen_valid and antigravity_valid:
        return "REAL_PLANNER_SHOOTOUT_VALID"
    if qwen_valid:
        return "QWEN_REAL_ANTIGRAVITY_INVALID"
    if antigravity_valid:
        return "ANTIGRAVITY_REAL_QWEN_INVALID"
    return "BOTH_PLANNERS_INVALID"


def perform_real_planner_audit(
    brief: ContentLockSpec | None = None,
    qwen_planner: RealQwenDesignPlanner | None = None,
    antigravity_planner: RealAntigravityDesignPlanner | None = None,
    *,
    execute: bool = False,
) -> dict[str, Any]:
    """Audit planner provenance.

    ``execute`` defaults to ``False`` so CI and routine tooling never accidentally
    loads a local LLM or mistakes the historical synthetic Antigravity path for a
    live agent invocation. A future Codex-controlled audit must opt in explicitly.
    """
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    if not execute:
        return {
            "schema_version": "2.0",
            "timestamp": timestamp,
            "conclusion": "PLANNER_SHOOTOUT_FROZEN",
            "benchmark_valid": False,
            "execution_performed": False,
            "reason": (
                "Planner shootout is quarantined. Explicit execute=True plus provenance "
                "flags proving AI-output-derived DesignPlanV2 are required."
            ),
            "qwen": {"valid": False, "status": "NOT_EXECUTED"},
            "antigravity": {"valid": False, "status": "NOT_EXECUTED"},
        }

    if brief is None:
        brief = get_brief_by_id("brief_sale_01")
    if qwen_planner is None:
        qwen_planner = RealQwenDesignPlanner()
    if antigravity_planner is None:
        antigravity_planner = RealAntigravityDesignPlanner(mode="mode_a_text")

    try:
        qwen_result = qwen_planner.plan(brief, candidate_index=0, seed=42)
        qwen_audit = _audit_qwen_result(qwen_result, brief)
    except Exception as exc:  # fail closed; exact runtime failure belongs in audit metadata
        qwen_audit = {
            "planner_name": getattr(qwen_planner, "name", "unknown"),
            "valid": False,
            "status": "EXECUTION_ERROR",
            "error_type": type(exc).__name__,
            "error": str(exc),
        }

    try:
        antigravity_result = antigravity_planner.plan(brief, candidate_index=0, seed=42)
        antigravity_audit = _audit_antigravity_result(antigravity_result, brief)
    except Exception as exc:
        antigravity_audit = {
            "planner_name": getattr(antigravity_planner, "name", "unknown"),
            "valid": False,
            "status": "EXECUTION_ERROR",
            "error_type": type(exc).__name__,
            "error": str(exc),
        }

    conclusion = _conclusion(
        bool(qwen_audit.get("valid")), bool(antigravity_audit.get("valid"))
    )
    return {
        "schema_version": "2.0",
        "timestamp": timestamp,
        "conclusion": conclusion,
        "benchmark_valid": conclusion == "REAL_PLANNER_SHOOTOUT_VALID",
        "execution_performed": True,
        "qwen": qwen_audit,
        "antigravity": antigravity_audit,
    }


def run_real_planner_pilot(
    output_root: Path = REAL_BENCHMARK_ROOT,
    mode: str = "mode_a_text",
    seed: int = 42,
    *,
    execute_audit: bool = False,
) -> dict[str, Any]:
    """Write the audit artifact and stop.

    Historical versions generated fake ``output.cdr`` files and a review queue from
    invalid planner provenance. The stabilized runner deliberately performs no
    candidate generation. Codex can rebuild the pilot only after both planners pass
    the v2 provenance audit.
    """
    del mode, seed
    output_root.mkdir(parents=True, exist_ok=True)
    audit_report = perform_real_planner_audit(execute=execute_audit)
    (output_root / "REAL_PLANNER_AUDIT.json").write_text(
        json.dumps(audit_report, indent=2), encoding="utf-8"
    )

    return {
        "status": "PLANNER_SHOOTOUT_FROZEN",
        "conclusion": audit_report["conclusion"],
        "benchmark_valid": audit_report["benchmark_valid"],
        "audit_report": audit_report,
        "pilot_generated": False,
        "total_pilot_candidates": 0,
        "pilot_pairs": 0,
        "human_review_ready": False,
        "review_queue_created": False,
        "real_cdr_verified": False,
        "commercial_allowed": False,
    }
