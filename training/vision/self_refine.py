"""Bounded render → critique → repair loop with a deterministic safety veto."""

from __future__ import annotations

import json
import time
from collections import Counter
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from training.evaluation.scoring import DesignScorer
from training.inference.corel_compiler import compile_corel_operations
from training.inference.preview import render_preview
from training.schemas.design import DesignDocument
from training.vision.critic import VisionCritic
from training.vision.models import RefinementPlanV1, SelfRefineIterationV1
from training.vision.refiner import (
    CritiqueToRefinementPlanner,
    apply_refinement_plan,
    business_content,
    validate_refinement,
)


def _write_json(path: Path, payload: Any) -> None:
    if hasattr(payload, "model_dump"):
        payload = payload.model_dump(mode="json")
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def _annotate(
    preview: Path,
    output: Path,
    document: DesignDocument,
    target_roles: list[str],
) -> None:
    image = Image.open(preview).convert("RGB")
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("arial.ttf", max(11, image.width // 70))
    except OSError:
        font = ImageFont.load_default()
    colors = ("#ff3b30", "#007aff", "#34c759")
    for index, role in enumerate(dict.fromkeys(target_roles)):
        for element in document.elements:
            actual = str(element.metadata.get("asset_role") or element.metadata.get("role") or "")
            if actual not in ({role} if role != "hero" else {"hero", "product"}):
                continue
            box = element.bbox_norm
            xy = (
                int(float(box.x) * image.width), int(float(box.y) * image.height),
                int(float(box.x + box.width) * image.width),
                int(float(box.y + box.height) * image.height),
            )
            color = colors[index % len(colors)]
            draw.rectangle(xy, outline=color, width=max(1, image.width // 300))
            draw.text((xy[0] + 3, xy[1] + 3), role.upper(), fill=color, font=font)
    image.save(output)


class SelfRefineEngine:
    def __init__(
        self,
        *,
        critic: VisionCritic,
        scorer: DesignScorer,
        planner: CritiqueToRefinementPlanner | None = None,
        max_iterations: int = 2,
        minimum_critic_improvement: float = .01,
    ) -> None:
        if not 1 <= max_iterations <= 3:
            raise ValueError("max_iterations must be between one and three")
        self.critic = critic
        self.scorer = scorer
        self.planner = planner or CritiqueToRefinementPlanner()
        self.max_iterations = max_iterations
        self.minimum_critic_improvement = minimum_critic_improvement

    def run(
        self,
        *,
        document: DesignDocument,
        brief: str,
        category: str,
        supplied_business_content: dict[str, object],
        asset_roles: list[str],
        output: Path,
    ) -> tuple[DesignDocument, dict[str, Any]]:
        started = time.perf_counter()
        output = output.resolve()
        output.mkdir(parents=True, exist_ok=True)
        original_content = business_content(document)
        baseline_overlap = float(
            self.scorer.technical_critic.score(document).metrics.get("overlap_ratio", 0)
        )
        issue_attempts: Counter[str] = Counter()
        versions: list[dict[str, Any]] = []
        current = document.model_copy(deep=True)
        stop_reason = "max_iterations_reached"
        previous_score: float | None = None
        for iteration in range(self.max_iterations + 1):
            iteration_started = time.perf_counter()
            iteration_dir = output / f"iteration_{iteration}"
            iteration_dir.mkdir(parents=True, exist_ok=True)
            design_path = iteration_dir / "design.json"
            _write_json(design_path, current)
            preview_path = render_preview(
                current,
                iteration_dir / "preview.png",
                max_dimension=1200,
                allow_upscale=True,
            )
            technical = validate_refinement(
                current,
                original_content=original_content,
                maximum_overlap=baseline_overlap,
            )
            _write_json(iteration_dir / "technical_validation.json", technical)
            corel = compile_corel_operations(
                current,
                width_mm=float(current.canvas.width),
                height_mm=float(current.canvas.height),
            )
            _write_json(iteration_dir / "corel_operations.json", corel)
            frozen = self.scorer.score(
                prompt=brief,
                document=current,
                preview_path=preview_path,
            )
            critique = self.critic.critique(
                preview_path=preview_path,
                brief=brief,
                category=category,
                business_content=supplied_business_content,
                asset_roles=asset_roles,
                document=current,
            )
            _write_json(iteration_dir / "vision_critique.json", critique)
            _annotate(
                preview_path,
                iteration_dir / "preview_annotated.png",
                current,
                [item.target_role for item in critique.issues],
            )
            selection_score = (
                .60 * float(critique.overall.quality_score)
                + .40 * float(frozen.final_score)
                if not technical.hard_failure
                else 0.0
            )
            iteration_record = SelfRefineIterationV1(
                iteration=iteration,
                critic_score=float(critique.overall.quality_score),
                frozen_design_score=float(frozen.final_score),
                selection_score=selection_score,
                technical_safe=not technical.hard_failure,
                accepted_operations=0,
                rejected_operations=0,
            )
            metrics = {
                "iteration": iteration_record.model_dump(mode="json"),
                "frozen_score": frozen.model_dump(mode="json"),
                "high_issue_count": sum(item.severity == "high" for item in critique.issues),
                "medium_issue_count": sum(item.severity == "medium" for item in critique.issues),
                "critic_latency_seconds": float(critique.latency_seconds),
                "iteration_latency_seconds": time.perf_counter() - iteration_started,
            }
            _write_json(iteration_dir / "metrics.json", metrics)
            versions.append(
                {
                    "record": iteration_record,
                    "document": current.model_copy(deep=True),
                    "critique": critique,
                    "technical": technical,
                    "preview_path": preview_path,
                    "iteration_dir": iteration_dir,
                    "metrics": metrics,
                }
            )
            if iteration >= self.max_iterations:
                _write_json(iteration_dir / "refinement_plan.json", RefinementPlanV1())
                _write_json(iteration_dir / "refinement_report.json", [])
                break
            if previous_score is not None:
                delta = float(critique.overall.quality_score) - previous_score
                if delta < self.minimum_critic_improvement:
                    stop_reason = "critic_improvement_below_threshold"
                    _write_json(iteration_dir / "refinement_plan.json", RefinementPlanV1())
                    _write_json(iteration_dir / "refinement_report.json", [])
                    break
                if not any(item.severity == "high" for item in critique.issues):
                    stop_reason = "no_high_severity_issues_remain"
                    _write_json(iteration_dir / "refinement_plan.json", RefinementPlanV1())
                    _write_json(iteration_dir / "refinement_report.json", [])
                    break
            plan = self.planner.plan(critique, issue_attempts=issue_attempts)
            _write_json(iteration_dir / "refinement_plan.json", plan)
            if not plan.operations:
                stop_reason = "no_safe_operations_or_all_issues_stalled"
                _write_json(iteration_dir / "refinement_report.json", [])
                break
            for operation in plan.operations:
                issue_attempts[operation.source_issue] += 1
            refined, reports, _ = apply_refinement_plan(current, plan)
            _write_json(iteration_dir / "refinement_report.json", reports)
            accepted = sum(item.accepted for item in reports)
            rejected = len(reports) - accepted
            versions[-1]["record"] = iteration_record.model_copy(
                update={"accepted_operations": accepted, "rejected_operations": rejected}
            )
            versions[-1]["metrics"]["iteration"] = versions[-1]["record"].model_dump(mode="json")
            _write_json(iteration_dir / "metrics.json", versions[-1]["metrics"])
            if accepted == 0:
                stop_reason = "technical_gate_rejected_all_operations"
                break
            previous_score = float(critique.overall.quality_score)
            current = refined
        eligible = [item for item in versions if item["record"].technical_safe]
        best = max(
            eligible,
            key=lambda item: (item["record"].selection_score, -item["record"].iteration),
        )
        final_dir = output / "final"
        final_dir.mkdir(exist_ok=True)
        best_document: DesignDocument = best["document"]
        _write_json(final_dir / "design.json", best_document)
        final_preview = render_preview(
            best_document,
            final_dir / "preview.png",
            max_dimension=1200,
            allow_upscale=True,
        )
        _write_json(
            final_dir / "corel_operations.json",
            compile_corel_operations(
                best_document,
                width_mm=float(best_document.canvas.width),
                height_mm=float(best_document.canvas.height),
            ),
        )
        summary = {
            "schema_version": "1.0",
            "iterations_executed": len(versions) - 1,
            "selected_iteration": best["record"].iteration,
            "selection_policy": "technical gate, then 0.60 critic + 0.40 frozen design score",
            "stop_reason": stop_reason,
            "initial_critic_score": versions[0]["record"].critic_score,
            "final_critic_score": best["record"].critic_score,
            "quality_delta": best["record"].critic_score - versions[0]["record"].critic_score,
            "initial_frozen_score": versions[0]["record"].frozen_design_score,
            "final_frozen_score": best["record"].frozen_design_score,
            "accepted_refinement_count": sum(item["record"].accepted_operations for item in versions),
            "rejected_refinement_count": sum(item["record"].rejected_operations for item in versions),
            "stalled_issue_count": sum(count >= 2 for count in issue_attempts.values()),
            "business_content_immutable": business_content(best_document) == original_content,
            "human_preference_collected": False,
            "vision_critic_preference_is_human_preference": False,
            "final_preview": str(final_preview),
            "total_self_refine_latency_seconds": time.perf_counter() - started,
            "iterations": [item["record"].model_dump(mode="json") for item in versions],
        }
        _write_json(output / "self_refine_summary.json", summary)
        return best_document, summary


__all__ = ["SelfRefineEngine"]
