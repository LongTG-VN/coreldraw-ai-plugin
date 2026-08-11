"""Replay v0.3 winners through the deterministic v0.3.1 visual engine."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from statistics import mean
from typing import Any

from PIL import Image, ImageDraw

from training.evaluation.critics import HeuristicAestheticCritic
from training.evaluation.layout_metrics import evaluate_layout
from training.evaluation.manual_review import write_manual_review_artifacts
from training.evaluation.scoring import DesignScorer, ScoreWeights
from training.inference.corel_compiler import compile_corel_operations
from training.inference.preview import render_preview
from training.retrieval.models import StructuredBriefV1
from training.schemas.design import DesignDocument
from training.typography.fitting import fit_design_typography
from training.visual import apply_visual_composition, evaluate_visual_quality, get_visual_profile


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _scorer(path: Path) -> DesignScorer:
    payload = _read_json(path)
    return DesignScorer(
        weights=ScoreWeights.model_validate(payload["weights"]),
        aesthetic_critic=HeuristicAestheticCritic(),
    )


def _flatten_score(score: Any) -> dict[str, Any]:
    payload = score.model_dump(mode="json")
    metrics = dict(payload["technical"]["metrics"])
    metrics.update(
        {
            "combined": payload["final_score"],
            "technical": payload["technical"]["overall"],
            "aesthetic": payload["aesthetic"]["overall"] if payload["aesthetic"] else 0.0,
            "eligible": payload["eligible"],
        }
    )
    return metrics


def _reference_rows(run_dir: Path) -> list[dict[str, Any]]:
    retrieval = _read_json(run_dir / "retrieval.json")
    return [
        {
            "reference_id": item["reference_id"],
            "score": item["score"],
            "match": item["match"],
        }
        for item in retrieval["results"]
    ]


def _contact_sheet(paths: list[tuple[str, Path]], output: Path) -> None:
    panels: list[tuple[str, Image.Image]] = []
    try:
        for label, path in paths:
            with Image.open(path) as source:
                image = source.convert("RGB")
                image.thumbnail((1200, 420), Image.Resampling.LANCZOS)
                panels.append((label, image.copy()))
        width = max((image.width for _, image in panels), default=800) + 40
        height = sum(image.height + 54 for _, image in panels) + 20
        canvas = Image.new("RGB", (width, height), "#F4F4F4")
        draw = ImageDraw.Draw(canvas)
        y = 16
        for label, image in panels:
            draw.text((20, y), label, fill="black")
            y += 30
            canvas.paste(image, ((width - image.width) // 2, y))
            y += image.height + 24
        canvas.save(output, format="PNG", optimize=False)
    finally:
        for _, image in panels:
            image.close()


def replay(*, source: Path, output: Path, score_config: Path) -> dict[str, Any]:
    source = source.resolve()
    output = output.resolve()
    if not (source / "runs").is_dir():
        raise FileNotFoundError(f"benchmark runs directory not found: {source / 'runs'}")
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"replay output must be new or empty: {output}")
    output.mkdir(parents=True, exist_ok=True)
    runs_output = output / "runs"
    runs_output.mkdir()
    scorer = _scorer(score_config.resolve())
    rows: list[dict[str, Any]] = []
    comparison_paths: list[tuple[str, Path]] = []
    for source_run in sorted((source / "runs").iterdir()):
        if not source_run.is_dir():
            continue
        prompt_id = source_run.name
        request = _read_json(source_run / "request.json")
        brief = StructuredBriefV1.model_validate(_read_json(source_run / "brief.json"))
        baseline = DesignDocument.model_validate(_read_json(source_run / "final" / "design.json"))
        destination = runs_output / prompt_id
        destination.mkdir()
        before_dir = destination / "v0.3"
        after_dir = destination / "v0.3.1_visual"
        before_dir.mkdir()
        after_dir.mkdir()
        shutil.copy2(source_run / "final" / "design.json", before_dir / "design.json")
        shutil.copy2(source_run / "final" / "preview.png", before_dir / "preview.png")

        retrieval = _read_json(source_run / "retrieval.json")
        reference_palette = (
            retrieval["results"][0].get("summary", {}).get("palette", [])
            if retrieval.get("results")
            else []
        )
        visual, report = apply_visual_composition(
            baseline,
            brief=brief,
            reference_palette=reference_palette,
            benchmark_mode=True,
        )
        fitted, typography = fit_design_typography(visual, allow_expand=False)
        fitted = DesignDocument.model_validate(fitted.model_dump())
        preview = render_preview(fitted, after_dir / "preview.png")
        operations = compile_corel_operations(
            fitted,
            width_mm=float(request["width_mm"]),
            height_mm=float(request["height_mm"]),
        )
        _write_json(after_dir / "design.json", fitted.model_dump(mode="json"))
        _write_json(after_dir / "corel_operations.json", operations)
        _write_json(after_dir / "visual_composition.json", report.model_dump(mode="json"))
        _write_json(after_dir / "typography.json", typography)

        winner = _read_json(source_run / "final" / "selection.json")["winner"]
        before_score_payload = _read_json(source_run / "candidates" / winner / "score.json")
        before_metrics = dict(before_score_payload["technical"]["metrics"])
        before_metrics.update(
            {
                "combined": before_score_payload["final_score"],
                "technical": before_score_payload["technical"]["overall"],
                "aesthetic": before_score_payload["aesthetic"]["overall"],
            }
        )
        after_score = scorer.score(
            prompt=str(request["prompt"]),
            document=fitted,
            preview_path=preview,
            validation={"raw_schema_valid": False},
        )
        after_metrics = _flatten_score(after_score)
        after_metrics["visual"] = evaluate_visual_quality(
            fitted,
            profile=get_visual_profile(brief.category, format_name=brief.format),
        )
        _write_json(after_dir / "metrics.json", after_metrics)
        comparison = write_manual_review_artifacts(
            prompt_id=prompt_id,
            prompt=str(request["prompt"]),
            v02_preview_path=before_dir / "preview.png",
            v02_metrics=before_metrics,
            v03_preview_path=after_dir / "preview.png",
            v03_metrics=after_metrics,
            v02_design_path=before_dir / "design.json",
            v03_design_path=after_dir / "design.json",
            retrieved_references=_reference_rows(source_run),
            output_dir=destination,
            left_key="v0.3",
            right_key="v0.3.1",
            left_label="V0.3 clean",
            right_label="V0.3.1 visual",
            artifact_type="v0.3_vs_v0.3.1_visual_replay",
        )
        comparison_paths.append((prompt_id, comparison["side_by_side"]))
        row = {
            "prompt_id": prompt_id,
            "prompt": request["prompt"],
            "before": before_metrics,
            "after": after_metrics,
            "visual_report": report.model_dump(mode="json"),
            "strict_schema_valid": True,
            "corel_operation_count": len(operations),
            "preview_exists": preview.is_file(),
            "comparison_path": str(comparison["html"]),
        }
        rows.append(row)
        _write_json(destination / "replay.json", row)

    metric_names = (
        "combined",
        "technical",
        "overlap_ratio",
        "spacing_score",
        "headline_dominance",
        "text_fit_rate",
        "coverage",
    )
    aggregates: dict[str, dict[str, float]] = {}
    for metric in metric_names:
        before_values = [float(row["before"].get(metric, 0)) for row in rows]
        after_values = [float(row["after"].get(metric, 0)) for row in rows]
        aggregates[metric] = {
            "before": mean(before_values),
            "after": mean(after_values),
            "delta": mean(after_values) - mean(before_values),
        }
    visual_names = (
        "density_fit",
        "palette_cohesion",
        "contrast",
        "headline_dominance",
        "cta_prominence",
        "typography_differentiation",
        "asset_intent_preservation",
        "decorative_balance",
        "focal_point_strength",
    )
    visual_averages = {
        name: mean(float(row["after"]["visual"][name]) for row in rows)
        for name in visual_names
    }
    summary = {
        "schema_version": "1.0",
        "artifact_type": "v0.3.1_visual_artifact_replay",
        "source": str(source),
        "prompt_count": len(rows),
        "fresh_model_generations": 0,
        "strict_schema_valid": sum(row["strict_schema_valid"] for row in rows),
        "corel_compile_success": sum(row["corel_operation_count"] > 0 for row in rows),
        "preview_success": sum(row["preview_exists"] for row in rows),
        "human_reviewed": False,
        "human_preference_collected": False,
        "scorer_changed": False,
        "aggregates": aggregates,
        "visual_averages": visual_averages,
        "business_data_policy": {
            "fake_customer_prices_allowed": False,
            "missing_values_use_explicit_placeholders": True,
            "benchmark_placeholder_provenance": True,
        },
    }
    _write_json(output / "replay_rows.json", rows)
    _write_json(output / "replay_summary.json", summary)
    _contact_sheet(comparison_paths, output / "contact_sheet_all_13.png")
    links = "\n".join(
        f'<li><a href="runs/{row["prompt_id"]}/comparison.html">{row["prompt_id"]}</a></li>'
        for row in rows
    )
    (output / "index.html").write_text(
        "<!doctype html><html><head><meta charset=\"utf-8\"><title>v0.3.1 visual replay</title></head>"
        "<body><h1>v0.3 vs v0.3.1 visual replay</h1>"
        "<p>Human review pending; heuristic scores are not human preference.</p>"
        '<p><img src="contact_sheet_all_13.png" style="max-width:100%"></p>'
        f"<ul>{links}</ul></body></html>\n",
        encoding="utf-8",
    )
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--score-config",
        type=Path,
        default=Path("training/config/scoring/aesthetic_v0_3.json"),
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    summary = replay(source=args.source, output=args.output, score_config=args.score_config)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
