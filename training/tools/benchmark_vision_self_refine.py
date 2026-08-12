"""Run bounded v0.3.5 self-refinement on selected v0.3.3 real-asset cases."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from statistics import mean

from PIL import Image, ImageDraw, ImageFont

from training.evaluation.critics import HeuristicAestheticCritic
from training.evaluation.scoring import DesignScorer, ScoreWeights
from training.schemas.design import DesignDocument
from training.tools.calibrate_vision_critic import blinded_order
from training.vision.critic import TransformersQwenVisionCritic
from training.vision.models import VisionCriticConfig
from training.vision.self_refine import SelfRefineEngine
from training.visual.profiles import normalize_visual_category


ALL_CASES = ("spa", "cafe", "sale", "menu", "signage")


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: object) -> None:
    if hasattr(payload, "model_dump"):
        payload = payload.model_dump(mode="json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def _scorer(path: Path) -> DesignScorer:
    return DesignScorer(
        weights=ScoreWeights.model_validate(_read(path)["weights"]),
        aesthetic_critic=HeuristicAestheticCritic(),
    )


def _font(size: int):
    for candidate in ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/segoeui.ttf"):
        if Path(candidate).is_file():
            return ImageFont.truetype(candidate, size=size)
    return ImageFont.load_default()


def _comparison(case_id: str, old: Path, new: Path, output: Path) -> None:
    images = [Image.open(path).convert("RGB") for path in (old, new)]
    display = (500, 500)
    cells = []
    for image in images:
        image.thumbnail(display, Image.Resampling.LANCZOS)
        cell = Image.new("RGB", display, "#ece8df")
        cell.paste(image, ((display[0] - image.width) // 2, (display[1] - image.height) // 2))
        cells.append(cell)
    sheet = Image.new("RGB", (1000, 555), "white")
    sheet.paste(cells[0], (0, 55)); sheet.paste(cells[1], (500, 55))
    draw = ImageDraw.Draw(sheet)
    draw.text((18, 12), f"{case_id.upper()} — V0.3.3 BASELINE", fill="#111", font=_font(22))
    draw.text((518, 12), "V0.3.5 SELF-REFINED", fill="#111", font=_font(22))
    sheet.save(output)


def _build_contact(output: Path, rows: list[dict]) -> None:
    images = [Image.open(output / "runs" / row["case_id"] / "comparison.png").convert("RGB") for row in rows]
    sheet = Image.new("RGB", (1000, 555 * len(images)), "white")
    y = 0
    for image in images:
        sheet.paste(image, (0, y)); y += 555
    sheet.save(output / "contact_sheet_v033_vs_v035_real_assets.png")


def _existing_rows(output: Path) -> list[dict]:
    rows = []
    for case_id in ALL_CASES:
        path = output / "runs" / case_id / "benchmark_row.json"
        if path.is_file():
            rows.append(_read(path))
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--benchmark-config", type=Path, required=True)
    parser.add_argument("--critic-config", type=Path, required=True)
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--score-config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cases", nargs="+", choices=ALL_CASES, required=True)
    parser.add_argument("--max-iterations", type=int, default=2)
    args = parser.parse_args()
    source, output = args.source.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    prompts = {row["id"]: row for row in _read(args.benchmark_config.resolve())["prompts"]}
    config = VisionCriticConfig.model_validate(_read(args.critic_config.resolve()))
    critic = TransformersQwenVisionCritic(config, local_model_path=args.model_path.resolve())
    scorer = _scorer(args.score_config.resolve())
    for case_id in args.cases:
        run = output / "runs" / case_id
        if run.exists():
            raise FileExistsError(f"refusing to overwrite existing self-refine run: {run}")
        print(f"self-refining {case_id}", flush=True)
        root = source / "runs" / case_id
        case = _read(root / "case.json")
        manifest = _read(root / "asset_manifest.json")
        prompt = prompts[case["source_prompt_id"]]["prompt"]
        category = normalize_visual_category(case_id)
        roles = sorted({str(row["role"]) for row in manifest.get("assets", [])})
        baseline = DesignDocument.model_validate_json(
            (root / "asset_aware" / "design.json").read_text(encoding="utf-8")
        )
        engine = SelfRefineEngine(
            critic=critic,
            scorer=scorer,
            max_iterations=args.max_iterations,
        )
        final, summary = engine.run(
            document=baseline,
            brief=prompt,
            category=category,
            supplied_business_content=case,
            asset_roles=roles,
            output=run,
        )
        baseline_preview = root / "asset_aware" / "preview.png"
        final_preview = run / "final" / "preview.png"
        shutil.copy2(baseline_preview, run / "v033_baseline.png")
        _comparison(case_id, baseline_preview, final_preview, run / "comparison.png")
        image_a, image_b, mapping = blinded_order(case_id + ":v035", baseline_preview, final_preview)
        pairwise = critic.compare(
            image_a=image_a, image_b=image_b, brief=prompt, category=category
        )
        _write(run / "pairwise_vision_judgment.json", pairwise)
        _write(run / "pairwise_private_mapping.json", mapping)
        generic_preferred = mapping.get(pairwise.preferred, "tie")
        preferred = {
            "v0.3.2": "v0.3.3",
            "v0.3.3": "v0.3.5",
        }.get(generic_preferred, "tie")
        selected_dir = run / f"iteration_{summary['selected_iteration']}"
        technical = _read(selected_dir / "technical_validation.json")
        initial_metrics = _read(run / "iteration_0" / "metrics.json")
        final_metrics = _read(selected_dir / "metrics.json")
        row = {
            "case_id": case_id,
            "initial_critic_score": summary["initial_critic_score"],
            "final_critic_score": summary["final_critic_score"],
            "quality_delta": summary["quality_delta"],
            "iterations_executed": summary["iterations_executed"],
            "selected_iteration": summary["selected_iteration"],
            "accepted_refinement_count": summary["accepted_refinement_count"],
            "rejected_refinement_count": summary["rejected_refinement_count"],
            "initial_frozen_score": summary["initial_frozen_score"],
            "final_frozen_score": summary["final_frozen_score"],
            "technical_safe": not technical["hard_failure"],
            "outside_canvas_rate": technical["outside_canvas_rate"],
            "overlap_ratio": technical["overlap_ratio"],
            "text_fit_rate": technical["text_fit_rate"],
            "corel_compile_valid": technical["corel_compile_valid"],
            "business_content_immutable": technical["business_content_immutable"],
            "pairwise_preferred": preferred,
            "pairwise_confidence": pairwise.confidence,
            "critic_latency_seconds": sum(
                item["critic_latency_seconds"]
                for item in [initial_metrics, *([] if selected_dir == run / "iteration_0" else [final_metrics])]
            ),
            "total_self_refine_latency_seconds": summary["total_self_refine_latency_seconds"],
            "comparison_path": str(run / "comparison.png"),
        }
        _write(run / "benchmark_row.json", row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
    rows = _existing_rows(output)
    _build_contact(output, rows)
    summary = {
        "schema_version": "1.0",
        "case_count": len(rows),
        "positive_critic_delta_count": sum(row["quality_delta"] > 0 for row in rows),
        "pairwise_v035_preferred_count": sum(row["pairwise_preferred"] == "v0.3.5" for row in rows),
        "pairwise_v033_preferred_count": sum(row["pairwise_preferred"] == "v0.3.3" for row in rows),
        "pairwise_tie_count": sum(row["pairwise_preferred"] == "tie" for row in rows),
        "technically_safe_count": sum(row["technical_safe"] for row in rows),
        "mean_quality_delta": mean(row["quality_delta"] for row in rows),
        "average_critic_latency_seconds": mean(row["critic_latency_seconds"] for row in rows),
        "average_total_self_refine_latency_seconds": mean(row["total_self_refine_latency_seconds"] for row in rows),
        "peak_vram_gib": critic.peak_memory_gib,
        "critic_load_seconds": critic.load_duration_seconds,
        "rows": rows,
        "human_preference_collected": False,
    }
    summary["machine_gate_pass"] = bool(
        len(rows) == 5
        and summary["technically_safe_count"] == 5
        and summary["positive_critic_delta_count"] >= 4
        and summary["pairwise_v035_preferred_count"] >= 4
        and all(row["business_content_immutable"] for row in rows)
    )
    _write(output / "benchmark_rows.json", rows)
    _write(output / "benchmark_summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
