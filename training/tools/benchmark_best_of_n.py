"""Benchmark single-shot candidate_01 against the winner of the same best-of-4 run."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from training.evaluation.critics import HeuristicAestheticCritic
from training.evaluation.scoring import DesignScorer, ScoreWeights
from training.inference.candidates import (
    BestOfNSelector,
    CandidateGenerationSettings,
    CandidateRecord,
)
from training.inference.qwen3_planner import Qwen3PlannerSession
from training.inference.qwen3_planner import RawPlannerGeneration
from training.preference.builder import export_preference


def _write(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _average(rows: list[dict], key: str) -> float:
    return statistics.mean(float(row[key]) for row in rows)


def _aesthetic_dimension(record: CandidateRecord, key: str) -> float:
    aesthetic = record.score.aesthetic
    return float(getattr(aesthetic, key)) if aesthetic is not None else 0.0


def _generation_key(
    *,
    prompt: str,
    width_mm: float,
    height_mm: float,
    seed: int,
    config: dict[str, Any],
) -> tuple[object, ...]:
    return (
        prompt,
        float(width_mm),
        float(height_mm),
        int(seed),
        int(config["max_new_tokens"]),
        bool(config["do_sample"]),
        float(config.get("temperature", 0.7)),
        float(config.get("top_p", 0.8)),
        int(config.get("top_k", 20)),
        float(config.get("repetition_penalty", 1.05)),
    )


class ReusingGenerator:
    """Reuse exact prior raw generations only when the full request key matches."""

    def __init__(
        self,
        *,
        live: Qwen3PlannerSession,
        cache_root: Path | None,
        expected_model: dict[str, Any],
    ) -> None:
        self.live = live
        self.cache: dict[tuple[object, ...], RawPlannerGeneration] = {}
        self.reuse_hits = 0
        self.cache_root = cache_root.resolve() if cache_root else None
        if self.cache_root is not None:
            self._load(expected_model)

    def _load(self, expected_model: dict[str, Any]) -> None:
        assert self.cache_root is not None
        for request_path in self.cache_root.glob("runs/*/request.json"):
            request = json.loads(request_path.read_text(encoding="utf-8"))
            model = request.get("model", {})
            if any(
                model.get(field) != expected_model.get(field)
                for field in ("model_id", "model_revision", "adapter_checkpoint")
            ):
                continue
            for candidate_dir in sorted((request_path.parent / "candidates").glob("candidate_*")):
                generation_path = candidate_dir / "generation.json"
                raw_path = candidate_dir / "raw_output.txt"
                if not generation_path.is_file() or not raw_path.is_file():
                    continue
                generation = json.loads(generation_path.read_text(encoding="utf-8"))
                config = generation["config"]
                key = _generation_key(
                    prompt=request["prompt"],
                    width_mm=request["width_mm"],
                    height_mm=request["height_mm"],
                    seed=generation["seed"],
                    config=config,
                )
                self.cache[key] = RawPlannerGeneration(
                    raw_output=raw_path.read_text(encoding="utf-8"),
                    duration_seconds=float(generation["duration_seconds"]),
                    seed=int(generation["seed"]),
                    generation_config={
                        **config,
                        "reused_raw_output": True,
                        "reused_from": str(candidate_dir.resolve()),
                    },
                    peak_vram_gib=float(generation["peak_vram_gib"]),
                )

    def generate_raw(self, **kwargs: Any) -> RawPlannerGeneration:
        key = _generation_key(
            prompt=str(kwargs["prompt"]),
            width_mm=float(kwargs["width_mm"]),
            height_mm=float(kwargs["height_mm"]),
            seed=int(kwargs["seed"]),
            config=kwargs,
        )
        cached = self.cache.get(key)
        if cached is not None:
            self.reuse_hits += 1
            return cached
        return self.live.generate_raw(**kwargs)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--model-config", type=Path, required=True)
    parser.add_argument(
        "--score-config",
        type=Path,
        default=Path("training/config/scoring/aesthetic_v0_2.json"),
    )
    parser.add_argument(
        "--benchmark-config",
        type=Path,
        default=Path("training/config/benchmarks/design_v0_2.json"),
    )
    parser.add_argument("--max-new-tokens", type=int, default=768)
    parser.add_argument("--base-seed", type=int, default=4200)
    parser.add_argument("--reuse-candidates-from", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"benchmark output already exists: {args.output}")
    args.output.mkdir(parents=True)

    model_config = json.loads(args.model_config.read_text(encoding="utf-8"))
    benchmark = json.loads(args.benchmark_config.read_text(encoding="utf-8"))
    score_config = json.loads(args.score_config.read_text(encoding="utf-8"))
    scorer = DesignScorer(
        weights=ScoreWeights.model_validate(score_config["weights"]),
        aesthetic_critic=HeuristicAestheticCritic(),
    )
    session = Qwen3PlannerSession(
        checkpoint=args.checkpoint,
        model_id=model_config["model_id"],
        model_revision=model_config["model_revision"],
    )
    provenance = {
        "generator": "qwen3_1_7b_local_qlora_v0.2",
        "model_id": model_config["model_id"],
        "model_revision": model_config["model_revision"],
        "adapter_checkpoint": str(args.checkpoint.resolve()),
        "trained_model": True,
    }
    generator = ReusingGenerator(
        live=session,
        cache_root=args.reuse_candidates_from,
        expected_model=provenance,
    )
    selector = BestOfNSelector(
        generator=generator,
        scorer=scorer,
        model_provenance=provenance,
    )
    rows = []
    for index, item in enumerate(benchmark["prompts"]):
        run_dir = args.output / "runs" / item["id"]
        max_new_tokens = int(item.get("max_new_tokens", args.max_new_tokens))
        result = selector.run(
            prompt=item["prompt"],
            width_mm=item["width_mm"],
            height_mm=item["height_mm"],
            settings=CandidateGenerationSettings(
                num_candidates=4,
                base_seed=args.base_seed + index * 10,
                max_new_tokens=max_new_tokens,
            ),
            run_dir=run_dir,
            raise_on_all_invalid=False,
        )
        single = result.candidates["candidate_01"]
        winner_id = result.ranking.winner
        winner = result.candidates[winner_id] if winner_id else single
        if winner_id is not None:
            export_preference(run_dir, run_dir / "preference.auto.json")
        durations = [
            float(record.generation["duration_seconds"])
            for record in result.candidates.values()
        ]
        rows.append(
            {
                "prompt_id": item["id"],
                "category": item["category"],
                "max_new_tokens": max_new_tokens,
                "single_candidate": "candidate_01",
                "single_score": single.score.final_score,
                "single_valid": single.score.eligible,
                "single_technical_score": single.score.technical.overall,
                "single_overlap": single.score.technical.metrics.get("overlap_ratio", 1),
                "single_outside": single.score.technical.metrics.get(
                    "outside_canvas_rate", 1
                ),
                "single_hierarchy": _aesthetic_dimension(
                    single, "visual_hierarchy"
                ),
                "single_spacing": _aesthetic_dimension(single, "spacing"),
                "single_text_fit": single.score.technical.metrics.get(
                    "text_fit_rate", 1
                ),
                "winner": winner_id,
                "best_of_4_score": (
                    winner.score.final_score if winner_id is not None else 0.0
                ),
                "best_of_4_valid": winner_id is not None,
                "best_of_4_technical_score": (
                    winner.score.technical.overall if winner_id is not None else 0.0
                ),
                "best_of_4_overlap": winner.score.technical.metrics.get(
                    "overlap_ratio", 1
                ),
                "best_of_4_outside": winner.score.technical.metrics.get(
                    "outside_canvas_rate", 1
                ),
                "best_of_4_hierarchy": _aesthetic_dimension(
                    winner, "visual_hierarchy"
                ),
                "best_of_4_spacing": _aesthetic_dimension(winner, "spacing"),
                "best_of_4_text_fit": winner.score.technical.metrics.get(
                    "text_fit_rate", 1
                ),
                "valid_candidate_count": sum(
                    record.score.eligible for record in result.candidates.values()
                ),
                "layout_diversity": result.diversity["average_layout_distance"],
                "generation_seconds": sum(durations),
                "average_candidate_seconds": sum(durations) / len(durations),
                "peak_vram_gib": max(
                    float(record.generation["peak_vram_gib"])
                    for record in result.candidates.values()
                ),
                "run_dir": str(run_dir.resolve()),
            }
        )
        print(json.dumps(rows[-1], ensure_ascii=False))

    single_average = _average(rows, "single_score")
    best_average = _average(rows, "best_of_4_score")
    improvement = (
        ((best_average - single_average) / single_average) * 100
        if single_average > 0
        else 0.0
    )
    target = float(benchmark["score_target_improvement_percent"])
    summary = {
        "benchmark_id": benchmark["benchmark_id"],
        "prompt_count": len(rows),
        "single_shot_average": single_average,
        "best_of_4_average": best_average,
        "improvement_percent": improvement,
        "target_improvement_percent": target,
        "target_passed": improvement >= target,
        "single_valid_rate": statistics.mean(row["single_valid"] for row in rows),
        "best_of_4_valid_rate": statistics.mean(
            row["best_of_4_valid"] for row in rows
        ),
        "average_valid_candidates": _average(rows, "valid_candidate_count"),
        "single_technical_score_average": _average(
            rows, "single_technical_score"
        ),
        "best_of_4_technical_score_average": _average(
            rows, "best_of_4_technical_score"
        ),
        "single_overlap_average": _average(rows, "single_overlap"),
        "best_of_4_overlap_average": _average(rows, "best_of_4_overlap"),
        "single_outside_average": _average(rows, "single_outside"),
        "best_of_4_outside_average": _average(rows, "best_of_4_outside"),
        "single_hierarchy_average": _average(rows, "single_hierarchy"),
        "best_of_4_hierarchy_average": _average(rows, "best_of_4_hierarchy"),
        "single_spacing_average": _average(rows, "single_spacing"),
        "best_of_4_spacing_average": _average(rows, "best_of_4_spacing"),
        "single_text_fit_average": _average(rows, "single_text_fit"),
        "best_of_4_text_fit_average": _average(rows, "best_of_4_text_fit"),
        "average_layout_diversity": _average(rows, "layout_diversity"),
        "average_candidate_seconds": _average(rows, "average_candidate_seconds"),
        "total_generation_seconds": sum(row["generation_seconds"] for row in rows),
        "peak_vram_gib": max(row["peak_vram_gib"] for row in rows),
        "model_load_seconds": session.load_duration_seconds,
        "reused_candidate_count": generator.reuse_hits,
        "reuse_source": (
            str(generator.cache_root) if generator.cache_root is not None else None
        ),
        "model": provenance,
        "critic": scorer.provenance(),
    }
    _write(args.output / "single_shot.json", [
        {"prompt_id": row["prompt_id"], "score": row["single_score"]}
        for row in rows
    ])
    _write(args.output / "best_of_4.json", [
        {"prompt_id": row["prompt_id"], "winner": row["winner"], "score": row["best_of_4_score"]}
        for row in rows
    ])
    _write(args.output / "benchmark_rows.json", rows)
    _write(args.output / "benchmark_summary.json", summary)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if summary["target_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
