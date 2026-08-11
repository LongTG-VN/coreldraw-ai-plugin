"""Replay RAG raw winners through recovery, reference layout, and visual stages."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from training.evaluation.ablation import ABLATION_VARIANTS, aggregate_ablation_rows
from training.evaluation.critics import HeuristicAestheticCritic
from training.evaluation.scoring import DesignScorer, ScoreWeights
from training.inference.corel_compiler import compile_corel_operations
from training.inference.preview import render_preview
from training.inference.qwen3_planner import parse_design_output
from training.inference.reference_layout import apply_reference_layout_guidance
from training.retrieval.models import ReferenceContextV1, StructuredBriefV1
from training.schemas.design import DesignDocument
from training.typography.fitting import fit_design_typography
from training.visual import apply_visual_composition, evaluate_visual_quality, get_visual_profile


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _score_metrics(score: Any) -> dict[str, float]:
    layout = score.technical.metrics
    aesthetic = score.aesthetic
    return {
        "combined": float(score.final_score),
        "technical": float(score.technical.overall),
        "overlap": float(layout.get("overlap_ratio", 0)),
        "spacing": float(aesthetic.spacing if aesthetic else 0),
        "hierarchy": float(aesthetic.visual_hierarchy if aesthetic else 0),
        "text_fit": float(layout.get("text_fit_rate", 0)),
        "coverage": float(layout.get("coverage", 0)),
    }


def _materialize_variant(
    *,
    variant: str,
    document: DesignDocument,
    prompt: str,
    width: float,
    height: float,
    validation: dict[str, Any],
    scorer: DesignScorer,
    output: Path,
    extra_report: dict[str, Any],
    brief: StructuredBriefV1,
) -> dict[str, Any]:
    output.mkdir()
    design = DesignDocument.model_validate(document.model_dump())
    preview = render_preview(design, output / "preview.png")
    operations = compile_corel_operations(design, width_mm=width, height_mm=height)
    score = scorer.score(
        prompt=prompt,
        document=design,
        preview_path=preview,
        validation=validation,
    )
    _write_json(output / "design.json", design.model_dump(mode="json"))
    _write_json(output / "corel_operations.json", operations)
    _write_json(output / "score.json", score.model_dump(mode="json"))
    _write_json(output / "stage_report.json", extra_report)
    payload = {
        "variant": variant,
        "strict_schema_valid": True,
        "corel_compile_success": bool(operations),
        "preview_exists": preview.is_file(),
        "metrics": _score_metrics(score),
        "artifact_path": str(output.resolve()),
    }
    if variant == "rag_reference_visual_full":
        payload["visual_metrics"] = evaluate_visual_quality(
            design,
            profile=get_visual_profile(brief.category, format_name=brief.format),
        )
    return payload


def run_ablation(*, source: Path, output: Path, score_config: Path) -> dict[str, Any]:
    source = source.resolve()
    output = output.resolve()
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"ablation output must be new or empty: {output}")
    output.mkdir(parents=True, exist_ok=True)
    runs_out = output / "runs"
    runs_out.mkdir()
    score_payload = _read_json(score_config.resolve())
    scorer = DesignScorer(
        weights=ScoreWeights.model_validate(score_payload["weights"]),
        aesthetic_critic=HeuristicAestheticCritic(),
    )
    rows = []
    for run_dir in sorted((source / "runs").iterdir()):
        if not run_dir.is_dir():
            continue
        prompt_id = run_dir.name
        request = _read_json(run_dir / "request.json")
        brief = StructuredBriefV1.model_validate(_read_json(run_dir / "brief.json"))
        context = ReferenceContextV1.model_validate(_read_json(run_dir / "reference_context.json"))
        winner = _read_json(run_dir / "ranking.json")["winner"]
        if not winner:
            raise ValueError(f"source run has no winner: {prompt_id}")
        raw_output = (run_dir / "candidates" / winner / "raw_output.txt").read_text(encoding="utf-8")
        recovered, validation = parse_design_output(
            raw_output,
            canvas_width=float(request["width_mm"]),
            canvas_height=float(request["height_mm"]),
        )
        recovered.metadata.update(
            {
                "trained_model": True,
                "ablation_source": "rag_grounded_raw_winner",
            }
        )
        recovered = DesignDocument.model_validate(recovered.model_dump())
        grounded, layout_report = apply_reference_layout_guidance(
            recovered,
            brief=brief,
            context=context,
            benchmark_mode=True,
        )
        reference_fitted, reference_type_report = fit_design_typography(
            grounded,
            allow_expand=False,
        )
        visual, visual_report = apply_visual_composition(
            grounded,
            brief=brief,
            reference_palette=context.references[0].palette if context.references else [],
            benchmark_mode=True,
        )
        visual_fitted, visual_type_report = fit_design_typography(
            visual,
            allow_expand=False,
        )
        destination = runs_out / prompt_id
        destination.mkdir()
        variants = {
            "rag_recovery_only": _materialize_variant(
                variant="rag_recovery_only",
                document=recovered,
                prompt=request["prompt"],
                width=float(request["width_mm"]),
                height=float(request["height_mm"]),
                validation=validation,
                scorer=scorer,
                output=destination / "rag_recovery_only",
                extra_report={"parse": validation},
                brief=brief,
            ),
            "rag_reference_layout_typography": _materialize_variant(
                variant="rag_reference_layout_typography",
                document=reference_fitted,
                prompt=request["prompt"],
                width=float(request["width_mm"]),
                height=float(request["height_mm"]),
                validation=validation,
                scorer=scorer,
                output=destination / "rag_reference_layout_typography",
                extra_report={"reference_layout": layout_report, "typography": reference_type_report},
                brief=brief,
            ),
            "rag_reference_visual_full": _materialize_variant(
                variant="rag_reference_visual_full",
                document=visual_fitted,
                prompt=request["prompt"],
                width=float(request["width_mm"]),
                height=float(request["height_mm"]),
                validation=validation,
                scorer=scorer,
                output=destination / "rag_reference_visual_full",
                extra_report={
                    "reference_layout": layout_report,
                    "visual_composition": visual_report.model_dump(mode="json"),
                    "typography": visual_type_report,
                },
                brief=brief,
            ),
        }
        row = {
            "prompt_id": prompt_id,
            "winner": winner,
            "rag_generation_shared_across_variants": True,
            "variants": variants,
        }
        rows.append(row)
        _write_json(destination / "ablation.json", row)
    report = {
        "schema_version": "1.0",
        "benchmark": "design_ai_v0.3_postprocessor_ablation_v1",
        "source": str(source),
        "variant_order": list(ABLATION_VARIANTS),
        "no_rag_generation_isolated": False,
        "no_rag_note": "All three stages share the same stored RAG-grounded raw winner; v0.2 remains the no-RAG comparison.",
        "fresh_model_generations": 0,
        "human_preference_collected": False,
        "aggregates": aggregate_ablation_rows(rows),
        "rows": rows,
    }
    _write_json(output / "ablation_summary.json", report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--score-config",
        type=Path,
        default=Path("training/config/scoring/aesthetic_v0_3.json"),
    )
    args = parser.parse_args()
    report = run_ablation(
        source=args.source,
        output=args.output,
        score_config=args.score_config,
    )
    print(json.dumps(report["aggregates"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
