from __future__ import annotations

from training.corel_operator.models import MutationActionV1, MutationPlanV1, TargetSelectorV1
from training.corel_operator.refinement import (
    BoundedRefinementPlanner,
    StructuredOperatorReviewV1,
)


def _plan() -> MutationPlanV1:
    return MutationPlanV1(
        plan_id="pilot",
        intent="bounded typography",
        source="deterministic",
        actions=[
            MutationActionV1(
                operation="set_font_size",
                target=TargetSelectorV1(kind="object_id", value="headline"),
                value=20.0,
            )
        ],
    )


def test_refinement_is_bounded_and_structured() -> None:
    review = StructuredOperatorReviewV1(
        source="deterministic",
        iteration=0,
        issues=[{"code": "TEXT_OVERFLOW", "object_id": "headline"}],
    )
    refined = BoundedRefinementPlanner().refine(_plan(), review)
    assert refined is not None
    assert refined.actions[0].value == 19.0
    assert refined.metadata["refinement_iteration"] == 1


def test_refinement_refuses_unsupported_visual_guess() -> None:
    review = StructuredOperatorReviewV1(
        source="llm",
        iteration=0,
        issues=[{"code": "COLLISION", "object_id": "headline"}],
    )
    assert BoundedRefinementPlanner().refine(_plan(), review) is None


def test_refinement_stops_at_three() -> None:
    review = StructuredOperatorReviewV1(
        source="human",
        iteration=3,
        issues=[{"code": "TEXT_OVERFLOW", "object_id": "headline"}],
    )
    assert BoundedRefinementPlanner().refine(_plan(), review) is None


def test_refinement_never_drops_below_readability_floor() -> None:
    plan = _plan()
    plan.actions[0].value = 6.0
    review = StructuredOperatorReviewV1(
        source="deterministic",
        iteration=1,
        issues=[{"code": "TEXT_OVERFLOW", "object_id": "headline"}],
    )
    assert BoundedRefinementPlanner(min_font_size=6.0).refine(plan, review) is None
