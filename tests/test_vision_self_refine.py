from __future__ import annotations

from pathlib import Path

import pytest

from training.evaluation.critics import HeuristicAestheticCritic
from training.evaluation.scoring import DesignScorer, ScoreWeights
from training.tools.build_reference_corpus import _generic_document
from training.tools.calibrate_vision_critic import blinded_order
from training.vision.critic import (
    TransformersQwenVisionCritic,
    VisionCriticError,
    _normalize_critique_payload,
    recover_json_object,
)
from training.vision.models import (
    CritiqueOverallV1,
    DesignIssueV1,
    VisionCriticConfig,
    VisionCritiqueV1,
)
from training.vision.refiner import (
    CritiqueToRefinementPlanner,
    apply_refinement_plan,
    business_content,
    validate_refinement,
)
from training.vision.self_refine import SelfRefineEngine


def _issue(issue_type: str = "weak_headline", role: str = "headline") -> DesignIssueV1:
    return DesignIssueV1.model_validate(
        {
            "issue_type": issue_type,
            "severity": "high",
            "confidence": .9,
            "target_role": role,
            "reason": "Observable fixture issue.",
            "recommended_action": "increase_emphasis",
            "magnitude": "small",
        }
    )


def _critique(score: float, issues: list[DesignIssueV1]) -> VisionCritiqueV1:
    return VisionCritiqueV1(
        overall=CritiqueOverallV1(quality_score=score, confidence=.9),
        issues=issues,
        critic_model="fixture/critic",
        critic_revision="one",
        latency_seconds=.01,
    )


def _scorer() -> DesignScorer:
    return DesignScorer(
        weights=ScoreWeights(
            technical=.25, composition=.15, visual_hierarchy=.15,
            typography=.10, spacing=.10, color_harmony=.08,
            balance=.05, readability=.10, prompt_match=.02,
        ),
        aesthetic_critic=HeuristicAestheticCritic(),
    )


class FakeCritic:
    config = VisionCriticConfig(model_id="fixture/critic", revision="one", quantization="none", device="cpu")
    loaded = False
    load_duration_seconds = 0.0
    peak_memory_gib = 0.0

    def __init__(self, outputs: list[VisionCritiqueV1]) -> None:
        self.outputs = list(outputs)

    def critique(self, **_: object) -> VisionCritiqueV1:
        self.loaded = True
        return self.outputs.pop(0)

    def compare(self, **_: object):
        raise NotImplementedError


def test_json_recovery_accepts_fence_but_rejects_truncated_prefix() -> None:
    payload, recovered = recover_json_object('```json\n{"overall": {"quality_score": 0.5}}\n```')
    assert payload["overall"]["quality_score"] == .5
    assert recovered is True
    with pytest.raises(VisionCriticError, match="no complete JSON"):
        recover_json_object('{"overall":{"quality_score":0.5}')


def test_issue_taxonomy_and_severity_are_strict() -> None:
    _issue()
    with pytest.raises(ValueError):
        _issue("execute_python", "layout")
    payload = _issue().model_dump()
    payload["severity"] = "catastrophic"
    with pytest.raises(ValueError):
        DesignIssueV1.model_validate(payload)


def test_bounded_recovery_normalizes_misplaced_confidence_without_free_commands() -> None:
    payload, changed = _normalize_critique_payload(
        {
            "overall": {"quality_score": .5, "confidence": .7},
            "issues": [{
                "issue_type": "weak_focal_point", "severity": .7,
                "target_role": "product", "reason": "Product is too small.",
                "recommended_action": "increase_area", "magnitude": "moderate",
            }],
        },
        max_issues=2,
    )
    assert changed is True
    assert payload["issues"][0]["severity"] == "medium"
    assert payload["issues"][0]["confidence"] == .7
    assert payload["issues"][0]["target_role"] == "hero"
    assert payload["issues"][0]["magnitude"] == "medium"


def test_planner_caps_operations_and_stalls_repeated_issue() -> None:
    critique = _critique(
        .4,
        [_issue(), _issue("weak_cta", "cta"), _issue("hero_too_small", "hero")],
    )
    planner = CritiqueToRefinementPlanner(max_operations=2, repeated_issue_limit=2)
    plan = planner.plan(critique)
    assert len(plan.operations) == 2
    assert all(float(op.parameters.get("factor", 1)) <= 1.12 for op in plan.operations)
    stalled = planner.plan(critique, issue_attempts={"weak_headline": 2})
    assert "weak_headline" in stalled.stalled_issues


def test_refinement_preserves_business_copy_and_passes_corel_gate() -> None:
    document = _generic_document("spa", "hero_right", ["cream", "gold"])
    original = business_content(document)
    plan = CritiqueToRefinementPlanner().plan(_critique(.4, [_issue()]))
    refined, reports, validation = apply_refinement_plan(document, plan)
    assert reports[0].accepted is True
    assert validation.hard_failure is False
    assert business_content(refined) == original
    assert validation.corel_compile_valid is True


def test_business_data_mutation_is_rejected() -> None:
    document = _generic_document("spa", "hero_right", ["red", "gold"])
    original = business_content(document)
    target = next(item for item in document.elements if item.text is not None)
    target.text.content = "GIẢM 99%"
    validation = validate_refinement(document, original_content=original, maximum_overlap=1)
    assert validation.hard_failure is True
    assert "business_content_mutated" in validation.violations


def test_outside_canvas_refinement_is_rejected_before_corel_compile() -> None:
    document = _generic_document("spa", "hero_right", ["cream", "gold"])
    original = business_content(document)
    target = next(item for item in document.elements if item.text is not None)
    target.bbox_norm.x = 1.01
    validation = validate_refinement(document, original_content=original, maximum_overlap=1)
    assert validation.hard_failure is True
    assert validation.schema_valid is False
    assert any(item.startswith("schema:") for item in validation.violations)


def test_overlap_regression_is_rejected() -> None:
    document = _generic_document("menu", "grid", ["cream", "green"])
    original = business_content(document)
    text_elements = [item for item in document.elements if item.text is not None]
    assert len(text_elements) >= 2
    text_elements[1].bbox = text_elements[0].bbox.model_copy(deep=True)
    text_elements[1].bbox_norm = text_elements[0].bbox_norm.model_copy(deep=True)
    validation = validate_refinement(document, original_content=original, maximum_overlap=0)
    assert validation.hard_failure is True
    assert "overlap_regression" in validation.violations


def test_self_refine_stops_after_positive_safe_iteration(tmp_path: Path) -> None:
    document = _generic_document("spa", "hero_right", ["cream", "gold"])
    critic = FakeCritic([_critique(.45, [_issue()]), _critique(.65, [])])
    engine = SelfRefineEngine(critic=critic, scorer=_scorer(), max_iterations=2)
    final, summary = engine.run(
        document=document,
        brief="Spa premium",
        category="spa",
        supplied_business_content={"headline": "SPA"},
        asset_roles=[],
        output=tmp_path / "run",
    )
    assert summary["quality_delta"] > 0
    assert summary["selected_iteration"] == 1
    assert summary["business_content_immutable"] is True
    assert (tmp_path / "run" / "iteration_0" / "vision_critique.json").is_file()
    assert (tmp_path / "run" / "iteration_1" / "technical_validation.json").is_file()
    assert final.schema_version == "0.1"


def test_real_critic_lifecycle_is_lazy_and_does_not_import_weights() -> None:
    critic = TransformersQwenVisionCritic(
        VisionCriticConfig(model_id="fixture/not-downloaded", revision="one")
    )
    assert critic.loaded is False
    assert critic.device == "not_loaded"


def test_pairwise_order_is_deterministic_and_blinded(tmp_path: Path) -> None:
    old, new = tmp_path / "old.png", tmp_path / "new.png"
    first = blinded_order("sale", old, new)
    second = blinded_order("sale", old, new)
    assert first == second
    assert set(first[2]) == {"A", "B"}
    assert set(first[2].values()) == {"v0.3.2", "v0.3.3"}
