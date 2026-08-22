"""Deterministic real-CDR ambiguity controls for the safe operator boundary."""

from __future__ import annotations

from typing import Any

from training.corel_operator.models import (
    MutationActionV1,
    MutationPlanV1,
    OperatorResultClass,
    TargetSelectorV1,
)


def build_ambiguous_text_control_plan(*, control_id: str) -> MutationPlanV1:
    """Build a selector that must match every page-one text object.

    The caller must preflight at least two page-one text objects.  The plan is
    therefore expected to stop at target resolution and never reach COM
    mutation.  It tests refusal behavior, not text editing.
    """

    return MutationPlanV1(
        plan_id=f"ambiguity-{control_id}",
        intent="verify that a deliberately non-unique text query is refused",
        source="deterministic",
        actions=[
            MutationActionV1(
                operation="replace_text",
                target=TargetSelectorV1(
                    kind="regex_text",
                    value=".*",
                    object_type="text",
                    page=1,
                    require_unique=True,
                ),
                value="BENCHMARK TEST",
                precondition_object_type="text",
            )
        ],
        metadata={
            "planner": "AmbiguousControlPlanner",
            "planner_is_ai": False,
            "ambiguous_control": True,
            "benchmark_sample_data": True,
        },
    )


def summarize_ambiguity_controls(payloads: list[dict[str, Any]]) -> dict[str, Any]:
    safely_refused = sum(
        item.get("result") == OperatorResultClass.NEEDS_REVIEW.value
        and item.get("error_code") == "TARGET_NOT_UNIQUE_OR_MISSING"
        and not bool(item.get("transaction_committed"))
        and bool(item.get("source_unchanged"))
        for item in payloads
    )
    return {
        "schema_version": "1.0",
        "planner_is_ai": False,
        "control_cases": len(payloads),
        "safely_refused": safely_refused,
        "unexpected_results": len(payloads) - safely_refused,
        "source_mutations": sum(
            not bool(item.get("source_unchanged")) for item in payloads
        ),
    }


__all__ = ["build_ambiguous_text_control_plan", "summarize_ambiguity_controls"]
