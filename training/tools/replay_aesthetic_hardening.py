"""Replay 13 v0.3.1 winners through deterministic v0.3.2 hardening."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from statistics import mean
from typing import Any

from PIL import Image, ImageDraw

from training.evaluation.critics import HeuristicAestheticCritic
from training.evaluation.manual_review import write_manual_review_artifacts
from training.evaluation.scoring import DesignScorer, ScoreWeights
from training.inference.corel_compiler import compile_corel_operations
from training.inference.preview import render_preview
from training.retrieval.models import StructuredBriefV1
from training.schemas.design import DesignDocument
from training.typography.fitting import fit_design_typography
from training.visual import apply_aesthetic_hardening, evaluate_aesthetic_hardening


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
    aesthetic = payload["aesthetic"] or {}
    metrics.update(
        {
            "combined": payload["final_score"],
            "technical": payload["technical"]["overall"],
            "aesthetic": aesthetic.get("overall", 0.0),
            "composition": aesthetic.get("composition", 0.0),
            "visual_hierarchy": aesthetic.get("visual_hierarchy", 0.0),
            "typography": aesthetic.get("typography", 0.0),
            "spacing": aesthetic.get("spacing", 0.0),
            "color_harmony": aesthetic.get("color_harmony", 0.0),
            "balance": aesthetic.get("balance", 0.0),
            "readability": aesthetic.get("readability", 0.0),
            "style_match": aesthetic.get("style_match", 0.0),
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
    cell_width, cell_height = 820, 500
    columns = 2
    rows = (len(paths) + columns - 1) // columns
    canvas = Image.new("RGB", (cell_width * columns, cell_height * rows), "#E9E7E3")
    draw = ImageDraw.Draw(canvas)
    for index, (prompt_id, path) in enumerate(paths):
        column, row = index % columns, index // columns
        origin_x, origin_y = column * cell_width, row * cell_height
        with Image.open(path) as source:
            pair = source.convert("RGB")
            pair.thumbnail((780, 430), Image.Resampling.LANCZOS)
        draw.text((origin_x + 20, origin_y + 16), prompt_id, fill="#181818")
        canvas.paste(pair, (origin_x + (cell_width - pair.width) // 2, origin_y + 50))
    canvas.save(output, format="PNG", optimize=False)


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
    comparisons: list[tuple[str, Path]] = []
    for source_run in sorted((source / "runs").iterdir()):
        if not source_run.is_dir():
            continue
        prompt_id = source_run.name
        request = _read_json(source_run / "request.json")
        brief = StructuredBriefV1.model_validate(_read_json(source_run / "brief.json"))
        baseline = DesignDocument.model_validate(_read_json(source_run / "final" / "design.json"))
        destination = runs_output / prompt_id
        before_dir = destination / "v0.3.1_clean"
        after_dir = destination / "v0.3.2_hardened"
        before_dir.mkdir(parents=True)
        after_dir.mkdir()
        shutil.copy2(source_run / "final" / "design.json", before_dir / "design.json")
        before_preview = render_preview(
            baseline,
            before_dir / "preview.png",
            max_dimension=1200,
            allow_upscale=True,
        )
        hardened, hardening_report = apply_aesthetic_hardening(baseline, brief=brief)
        fitted, typography = fit_design_typography(hardened, allow_expand=False)
        fitted = DesignDocument.model_validate(fitted.model_dump())
        after_preview = render_preview(
            fitted,
            after_dir / "preview.png",
            max_dimension=1200,
            allow_upscale=True,
        )
        operations = compile_corel_operations(
            fitted,
            width_mm=float(request["width_mm"]),
            height_mm=float(request["height_mm"]),
        )
        _write_json(after_dir / "design.json", fitted.model_dump(mode="json"))
        _write_json(after_dir / "corel_operations.json", operations)
        _write_json(after_dir / "aesthetic_hardening.json", hardening_report)
        _write_json(after_dir / "typography.json", typography)

        validation = {"raw_schema_valid": True, "strict_schema_valid": True}
        before_metrics = _flatten_score(
            scorer.score(
                prompt=str(request["prompt"]),
                document=baseline,
                preview_path=before_preview,
                validation=validation,
            )
        )
        after_metrics = _flatten_score(
            scorer.score(
                prompt=str(request["prompt"]),
                document=fitted,
                preview_path=after_preview,
                validation=validation,
            )
        )
        after_metrics["hardening"] = evaluate_aesthetic_hardening(fitted)
        _write_json(before_dir / "metrics.json", before_metrics)
        _write_json(after_dir / "metrics.json", after_metrics)
        comparison = write_manual_review_artifacts(
            prompt_id=prompt_id,
            prompt=str(request["prompt"]),
            v02_preview_path=before_preview,
            v02_metrics=before_metrics,
            v03_preview_path=after_preview,
            v03_metrics=after_metrics,
            v02_design_path=before_dir / "design.json",
            v03_design_path=after_dir / "design.json",
            retrieved_references=_reference_rows(source_run),
            output_dir=destination,
            left_key="v0.3.1",
            right_key="v0.3.2",
            left_label="V0.3.1 clean winner",
            right_label="V0.3.2 aesthetically hardened",
            artifact_type="v0.3.1_vs_v0.3.2_aesthetic_hardening",
        )
        comparisons.append((prompt_id, comparison["side_by_side"]))
        row = {
            "prompt_id": prompt_id,
            "prompt": request["prompt"],
            "before": before_metrics,
            "after": after_metrics,
            "hardening_report": hardening_report,
            "strict_schema_valid": True,
            "outside_canvas_safe": float(after_metrics["outside_canvas_rate"]) == 0,
            "text_truncated": int(typography["truncated_count"]),
            "corel_operation_count": len(operations),
            "comparison_path": str(comparison["html"]),
        }
        rows.append(row)
        _write_json(destination / "replay.json", row)

    metric_names = (
        "combined", "technical", "overlap_ratio", "spacing",
        "headline_dominance", "text_fit_rate", "coverage",
    )
    aggregates: dict[str, dict[str, float]] = {}
    for metric in metric_names:
        before_values = [float(row["before"].get(metric, 0)) for row in rows]
        after_values = [float(row["after"].get(metric, 0)) for row in rows]
        aggregates[metric] = {
            "v0.3.1": mean(before_values),
            "v0.3.2": mean(after_values),
            "delta": mean(after_values) - mean(before_values),
        }
    summary = {
        "schema_version": "1.0",
        "artifact_type": "v0.3.2_aesthetic_hardening_replay",
        "source": str(source),
        "prompt_count": len(rows),
        "fresh_model_generations": 0,
        "strict_schema_valid": sum(row["strict_schema_valid"] for row in rows),
        "outside_canvas_safe": sum(row["outside_canvas_safe"] for row in rows),
        "corel_compile_success": sum(row["corel_operation_count"] > 0 for row in rows),
        "no_truncation": sum(row["text_truncated"] == 0 for row in rows),
        "human_reviewed": False,
        "human_preference_collected": False,
        "scorer_changed": False,
        "content_generated": False,
        "aggregates": aggregates,
        "hardening_averages": {
            metric: mean(float(row["after"]["hardening"][metric]) for row in rows)
            for metric in (
                "placeholder_quality", "cta_prominence", "menu_readability",
                "decorative_balance",
            )
        },
        "business_data_policy": {
            "fake_customer_data_added": False,
            "missing_values_remain_explicit_placeholders": True,
        },
    }
    _write_json(output / "replay_rows.json", rows)
    _write_json(output / "summary.json", summary)
    _write_json(
        output / "review_notes.json",
        {
            "human_review_status": "pending",
            "human_preference_collected": False,
            "instruction": "Compare each v0.3.1/v0.3.2 pair; heuristic metrics are not human ratings.",
            "prompt_ids": [row["prompt_id"] for row in rows],
        },
    )
    _contact_sheet(comparisons, output / "contact_sheet_all_13.png")
    links = "\n".join(
        f'<li><a href="runs/{row["prompt_id"]}/comparison.html">{row["prompt_id"]}</a></li>'
        for row in rows
    )
    (output / "index.html").write_text(
        "<!doctype html><html><head><meta charset=\"utf-8\"><title>v0.3.2 aesthetic hardening</title>"
        "<style>body{font:16px Arial;max-width:1400px;margin:24px auto;background:#eee;color:#181818}"
        "img{max-width:100%;background:white}li{margin:8px}</style></head><body>"
        "<h1>V0.3.1 clean vs V0.3.2 aesthetic hardening</h1>"
        "<p>Human review pending. No model generation or scorer change was used.</p>"
        '<img src="contact_sheet_all_13.png" alt="13 prompt contact sheet">'
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
