"""Fair v0.2 best-of-4 replay versus v0.3 reference-grounded best-of-4.

The published v0.2 metrics remain immutable. All 52 stored v0.2 candidates are
rescored and reranked with the exact scorer used for the v0.3 candidates before
the comparison is calculated.
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import statistics
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from training.evaluation.critics import HeuristicAestheticCritic
from training.evaluation.diversity import candidate_diversity
from training.evaluation.manual_review import write_manual_review_artifacts
from training.evaluation.scoring import (
    CombinedScore,
    DesignScorer,
    ScoreWeights,
    rank_candidate_scores,
)
from training.inference.candidates import CandidateGenerationSettings
from training.inference.qwen3_planner import Qwen3PlannerSession, RawPlannerGeneration
from training.inference.rag import ReferenceGroundedDesignPipeline
from training.retrieval import JsonlReferenceProvider
from training.schemas.design import DesignDocument


DEFAULT_V02_BENCHMARK = Path(
    "training/artifacts/benchmarks/20260809_design_v0_2_best_of_4_final_v7"
)
DEFAULT_MODEL_CONFIG = Path(
    "training/config/experiments/qwen3_1_7b_local_qlora.json"
)
DEFAULT_SCORE_CONFIG = Path("training/config/scoring/aesthetic_v0_3.json")
DEFAULT_BENCHMARK_CONFIG = Path("training/config/benchmarks/design_v0_2.json")
SUCCESS_SCORE_IMPROVEMENT_PERCENT = 8.0


class ReusingRagGenerator:
    """Reuse exact saved RAG raw outputs while rerunning current postprocessing."""

    def __init__(self, live: Qwen3PlannerSession, cache_root: Path | None) -> None:
        self.live = live
        self.tokenizer = live.tokenizer
        self.cache_root = cache_root.resolve() if cache_root else None
        self.cache: dict[tuple[float, float, int, int], RawPlannerGeneration] = {}
        self.reuse_hits = 0
        if self.cache_root is not None:
            for request_path in self.cache_root.glob("runs/*/request.json"):
                request = _read_json(request_path)
                if request.get("reference_mode") != "rag":
                    continue
                for candidate_dir in (request_path.parent / "candidates").glob(
                    "candidate_*"
                ):
                    generation_path = candidate_dir / "generation.json"
                    raw_path = candidate_dir / "raw_output.txt"
                    if not generation_path.is_file() or not raw_path.is_file():
                        continue
                    generation = _read_json(generation_path)
                    config = generation["config"]
                    key = (
                        float(request["width_mm"]),
                        float(request["height_mm"]),
                        int(generation["seed"]),
                        int(config["max_new_tokens"]),
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
        key = (
            float(kwargs["width_mm"]),
            float(kwargs["height_mm"]),
            int(kwargs["seed"]),
            int(kwargs["max_new_tokens"]),
        )
        cached = self.cache.get(key)
        if cached is not None:
            self.reuse_hits += 1
            return cached
        return self.live.generate_raw(**kwargs)


def _read_json(path: Path) -> Any:
    if not path.is_file():
        raise FileNotFoundError(f"required JSON artifact does not exist: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def load_v03_scorer(score_config_path: Path) -> DesignScorer:
    config = _read_json(score_config_path.resolve())
    policy = config.get("comparison_policy")
    if policy != "rescore both v0.2 and v0.3 candidates with the same critic":
        raise ValueError("v0.3 score config must declare the fair comparison policy")
    return DesignScorer(
        weights=ScoreWeights.model_validate(config["weights"]),
        aesthetic_critic=HeuristicAestheticCritic(),
    )


def _aesthetic(score: CombinedScore, field: str) -> float:
    return float(getattr(score.aesthetic, field)) if score.aesthetic else 0.0


def _score_metrics(score: CombinedScore) -> dict[str, float | bool]:
    technical = score.technical.metrics
    return {
        "combined_score": float(score.final_score),
        "technical_score": float(score.technical.overall),
        "overlap": float(technical.get("overlap_ratio", 1.0)),
        "spacing": _aesthetic(score, "spacing"),
        "hierarchy": _aesthetic(score, "visual_hierarchy"),
        "text_fit": float(technical.get("text_fit_rate", 0.0)),
        "coverage": float(technical.get("coverage", 0.0)),
        "outside_canvas": float(technical.get("outside_canvas_rate", 1.0)),
        "schema_valid": bool(score.eligible),
    }


def replay_v02_prompt(
    *,
    prompt_id: str,
    prompt: str,
    width_mm: float,
    height_mm: float,
    run_dir: Path,
    scorer: DesignScorer,
    expected_candidate_count: int = 4,
) -> dict[str, Any]:
    """Rescore every stored candidate; never trust the historical winner/score."""

    source = run_dir.resolve()
    request = _read_json(source / "request.json")
    expected_request = {
        "prompt": prompt,
        "width_mm": float(width_mm),
        "height_mm": float(height_mm),
    }
    for field, expected in expected_request.items():
        actual = request.get(field)
        if field == "prompt":
            matches = actual == expected
        else:
            matches = math.isclose(float(actual), expected, rel_tol=0, abs_tol=1e-9)
        if not matches:
            raise ValueError(
                f"v0.2 request mismatch for {prompt_id}.{field}: {actual!r} != {expected!r}"
            )
    candidate_dirs = sorted((source / "candidates").glob("candidate_*"))
    if len(candidate_dirs) != expected_candidate_count:
        raise ValueError(
            f"{prompt_id} must contain {expected_candidate_count} stored candidates; "
            f"found {len(candidate_dirs)}"
        )

    scores: dict[str, CombinedScore] = {}
    documents: dict[str, DesignDocument] = {}
    generation_seconds: list[float] = []
    peak_vram: list[float] = []
    candidate_rows: list[dict[str, Any]] = []
    severe_outside_count = 0
    for candidate_dir in candidate_dirs:
        candidate_id = candidate_dir.name
        design_path = candidate_dir / "design.json"
        preview_path = candidate_dir / "preview.png"
        validation = _read_json(candidate_dir / "validation.json")
        if not preview_path.is_file():
            raise FileNotFoundError(f"stored preview does not exist: {preview_path}")
        document = DesignDocument.model_validate(_read_json(design_path))
        score = scorer.score(
            prompt=prompt,
            document=document,
            preview_path=preview_path,
            validation=validation,
        )
        generation = _read_json(candidate_dir / "generation.json")
        scores[candidate_id] = score
        documents[candidate_id] = document
        generation_seconds.append(float(generation["duration_seconds"]))
        peak_vram.append(float(generation["peak_vram_gib"]))
        metrics = _score_metrics(score)
        severe_outside_count += int(float(metrics["outside_canvas"]) > 0)
        candidate_rows.append(
            {
                "candidate_id": candidate_id,
                "seed": int(generation["seed"]),
                "metrics": metrics,
                "design_path": str(design_path.resolve()),
                "preview_path": str(preview_path.resolve()),
            }
        )

    ranking = rank_candidate_scores(scores)
    if ranking.winner is None:
        raise RuntimeError(f"fair replay produced no eligible v0.2 winner: {prompt_id}")
    winner_id = ranking.winner
    winner_dir = source / "candidates" / winner_id
    valid_documents = {
        candidate_id: documents[candidate_id]
        for candidate_id, score in scores.items()
        if score.eligible
    }
    diversity = candidate_diversity(valid_documents)
    settings = CandidateGenerationSettings.model_validate(request["generation"])
    return {
        "prompt_id": prompt_id,
        "source_run_dir": str(source),
        "comparison_basis": "fair_replay_with_v0.3_scorer",
        "winner": winner_id,
        "winner_preview_path": str((winner_dir / "preview.png").resolve()),
        "winner_design_path": str((winner_dir / "design.json").resolve()),
        "winner_metrics": _score_metrics(scores[winner_id]),
        "ranking": ranking.model_dump(mode="json"),
        "candidates": candidate_rows,
        "candidate_count": len(scores),
        "valid_candidate_count": sum(score.eligible for score in scores.values()),
        "candidate_validity_rate": statistics.mean(
            float(score.eligible) for score in scores.values()
        ),
        "severe_outside_candidate_count": severe_outside_count,
        "candidate_diversity": float(diversity["average_layout_distance"]),
        "total_candidate_generation_seconds": sum(generation_seconds),
        "average_candidate_generation_seconds": statistics.mean(generation_seconds),
        "peak_vram_gib": max(peak_vram),
        "generation_settings": settings.model_dump(mode="json"),
        "model": request.get("model", {}),
    }


def _retrieval_metrics(results: Sequence[Any]) -> dict[str, float]:
    if not results:
        return {
            "relevance": 0.0,
            "diversity": 0.0,
            "category_accuracy": 0.0,
            "format_match": 0.0,
            "style_relevance": 0.0,
        }
    return {
        "relevance": statistics.mean(float(item.match.relevance) for item in results),
        "diversity": statistics.mean(float(item.match.diversity) for item in results),
        "category_accuracy": statistics.mean(
            float(item.match.category) for item in results
        ),
        "format_match": statistics.mean(float(item.match.format) for item in results),
        "style_relevance": statistics.mean(float(item.match.style) for item in results),
    }


def _rag_row(result: Any) -> dict[str, Any]:
    selection = result.selection
    winner_id = selection.ranking.winner
    if winner_id is None:
        raise RuntimeError(f"RAG run produced no eligible winner: {selection.run_dir.name}")
    winner = selection.candidates[winner_id]
    candidate_rows = []
    severe_outside_count = 0
    for candidate_id, record in selection.candidates.items():
        metrics = _score_metrics(record.score)
        severe_outside_count += int(float(metrics["outside_canvas"]) > 0)
        candidate_rows.append(
            {
                "candidate_id": candidate_id,
                "seed": record.seed,
                "metrics": metrics,
                "design_path": (
                    str((record.directory / "design.json").resolve())
                    if record.document is not None
                    else None
                ),
                "preview_path": (
                    str(record.preview_path.resolve()) if record.preview_path else None
                ),
            }
        )
    generations = [record.generation for record in selection.candidates.values()]
    configs = [generation.get("config", {}) for generation in generations]
    return {
        "prompt_id": selection.run_dir.name,
        "run_dir": str(selection.run_dir.resolve()),
        "winner": winner_id,
        "winner_preview_path": str(winner.preview_path.resolve()),
        "winner_design_path": str((winner.directory / "design.json").resolve()),
        "winner_metrics": _score_metrics(winner.score),
        "ranking": selection.ranking.model_dump(mode="json"),
        "candidates": candidate_rows,
        "candidate_count": len(selection.candidates),
        "valid_candidate_count": sum(
            record.score.eligible for record in selection.candidates.values()
        ),
        "candidate_validity_rate": statistics.mean(
            float(record.score.eligible) for record in selection.candidates.values()
        ),
        "severe_outside_candidate_count": severe_outside_count,
        "candidate_diversity": float(
            selection.diversity["average_layout_distance"]
        ),
        "retrieval_latency_seconds": float(result.retrieval_latency_seconds),
        "total_candidate_generation_seconds": sum(
            float(item["duration_seconds"]) for item in generations
        ),
        "average_candidate_generation_seconds": statistics.mean(
            float(item["duration_seconds"]) for item in generations
        ),
        "peak_vram_gib": max(float(item["peak_vram_gib"]) for item in generations),
        "baseline_prompt_tokens": max(
            int(config.get("baseline_prompt_tokens", 0)) for config in configs
        ),
        "rag_prompt_tokens": max(
            int(config.get("rag_prompt_tokens", 0)) for config in configs
        ),
        "reference_prompt_token_delta": max(
            int(config.get("reference_prompt_token_delta", 0)) for config in configs
        ),
        "reference_context_estimated_tokens": int(result.context.estimated_tokens),
        "retrieval": _retrieval_metrics(result.retrieval),
        "retrieved_reference_count": len(result.retrieval),
    }


def _mean(rows: Sequence[Mapping[str, Any]], path: Sequence[str]) -> float:
    values = []
    for row in rows:
        current: Any = row
        for field in path:
            current = current[field]
        values.append(float(current))
    return statistics.mean(values)


def summarize_comparison(
    rows: Sequence[Mapping[str, Any]],
    *,
    scorer_provenance: Mapping[str, Any],
) -> dict[str, Any]:
    if not rows:
        raise ValueError("comparison rows cannot be empty")

    def aggregate(version: str) -> dict[str, Any]:
        result = {
            "combined_score": _mean(rows, (version, "winner_metrics", "combined_score")),
            "technical_score": _mean(rows, (version, "winner_metrics", "technical_score")),
            "overlap": _mean(rows, (version, "winner_metrics", "overlap")),
            "spacing": _mean(rows, (version, "winner_metrics", "spacing")),
            "hierarchy": _mean(rows, (version, "winner_metrics", "hierarchy")),
            "text_fit": _mean(rows, (version, "winner_metrics", "text_fit")),
            "coverage": _mean(rows, (version, "winner_metrics", "coverage")),
            "outside_canvas": _mean(rows, (version, "winner_metrics", "outside_canvas")),
            "schema_validity": _mean(rows, (version, "candidate_validity_rate")),
            "candidate_diversity": _mean(rows, (version, "candidate_diversity")),
            "average_candidate_latency_seconds": _mean(
                rows, (version, "average_candidate_generation_seconds")
            ),
            "average_total_prompt_runtime_seconds": _mean(
                rows, (version, "total_candidate_generation_seconds")
            ),
            "peak_vram_gib": max(float(row[version]["peak_vram_gib"]) for row in rows),
            "severe_outside_candidate_count": sum(
                int(row[version]["severe_outside_candidate_count"]) for row in rows
            ),
        }
        if version == "v0.3":
            result.update(
                {
                    "average_retrieval_latency_seconds": _mean(
                        rows, (version, "retrieval_latency_seconds")
                    ),
                    "baseline_prompt_tokens": _mean(
                        rows, (version, "baseline_prompt_tokens")
                    ),
                    "rag_prompt_tokens": _mean(rows, (version, "rag_prompt_tokens")),
                    "reference_prompt_token_delta": _mean(
                        rows, (version, "reference_prompt_token_delta")
                    ),
                    "reference_context_estimated_tokens": _mean(
                        rows, (version, "reference_context_estimated_tokens")
                    ),
                }
            )
            result["average_total_prompt_runtime_seconds"] += float(
                result["average_retrieval_latency_seconds"]
            )
        else:
            result["prompt_tokens"] = _mean(rows, (version, "prompt_tokens"))
        return result

    v02 = aggregate("v0.2")
    v03 = aggregate("v0.3")
    baseline_score = float(v02["combined_score"])
    improvement = (
        (float(v03["combined_score"]) - baseline_score) / baseline_score * 100
        if baseline_score > 0
        else 0.0
    )
    retrieval = {
        field: _mean(rows, ("v0.3", "retrieval", field))
        for field in (
            "relevance",
            "diversity",
            "category_accuracy",
            "format_match",
            "style_relevance",
        )
    }
    overlap_limit = float(v02["overlap"]) * 1.10
    gates = {
        "combined_score_improvement_at_least_8_percent": improvement
        >= SUCCESS_SCORE_IMPROVEMENT_PERCENT,
        "schema_validity_100_percent": math.isclose(
            float(v03["schema_validity"]), 1.0, rel_tol=0, abs_tol=1e-12
        ),
        "outside_canvas_zero_severe_cases": int(
            v03["severe_outside_candidate_count"]
        )
        == 0,
        "overlap_not_worse_than_v0.2_by_more_than_10_percent": float(
            v03["overlap"]
        )
        <= overlap_limit + 1e-12,
        "text_fit_strictly_better_than_v0.2": float(v03["text_fit"])
        > float(v02["text_fit"]),
        "hierarchy_not_worse_than_v0.2": float(v03["hierarchy"])
        >= float(v02["hierarchy"]),
    }
    return {
        "schema_version": "1.0",
        "benchmark": "design-ai-v0.3-reference-rag-fair-comparison",
        "comparison_policy": (
            "All stored v0.2 candidates and all v0.3 candidates were scored and "
            "reranked with the same v0.3 scorer. Published v0.2 metrics are retained "
            "for provenance and are not used as the fair gate baseline."
        ),
        "prompt_count": len(rows),
        "candidate_count_per_prompt": 4,
        "scorer": dict(scorer_provenance),
        "v0.2_fair_replay": v02,
        "v0.3_rag": v03,
        "retrieval": retrieval,
        "combined_score_improvement_percent": improvement,
        "success_target_percent": SUCCESS_SCORE_IMPROVEMENT_PERCENT,
        "success_gates": gates,
        "v0.3_complete": all(gates.values()),
    }


def _manual_reference_records(
    results: Sequence[Any], *, reference_root: Path | None = None
) -> list[dict[str, Any]]:
    return [
        {
            "reference_id": item.reference_id,
            "score": float(item.score),
            "match": item.match.model_dump(mode="json"),
            "category": item.metadata.category,
            "format": item.metadata.format,
            "summary": item.summary.model_dump(mode="json"),
            "source": item.metadata.source,
            "license": item.metadata.license,
            "license_class": item.metadata.license_class,
            "research_only": item.metadata.research_only,
            "commercial_allowed": item.metadata.commercial_allowed,
            **(
                {
                    "preview_path": str(
                        (reference_root / item.metadata.preview_path).resolve()
                    ),
                    "design_document_path": str(
                        (reference_root / item.metadata.design_document_path).resolve()
                    ),
                }
                if reference_root is not None
                else {}
            ),
        }
        for item in results
    ]


def run_benchmark(args: argparse.Namespace) -> dict[str, Any]:
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError(f"benchmark output already exists: {output}")
    v02_root = args.v02_benchmark.resolve()
    published_summary_path = v02_root / "benchmark_summary.json"
    published_summary = _read_json(published_summary_path)
    benchmark = _read_json(args.benchmark_config.resolve())
    if len(benchmark["prompts"]) != 13:
        raise ValueError("v0.3 fair benchmark requires the same 13 v0.2 prompts")
    scorer = load_v03_scorer(args.score_config)
    reference_provider = JsonlReferenceProvider(args.reference_index.resolve())

    output.mkdir(parents=True)
    shutil.copyfile(published_summary_path, output / "v0.2_published_summary.json")
    replay_rows: dict[str, dict[str, Any]] = {}
    for item in benchmark["prompts"]:
        prompt_id = item["id"]
        replay = replay_v02_prompt(
            prompt_id=prompt_id,
            prompt=item["prompt"],
            width_mm=float(item["width_mm"]),
            height_mm=float(item["height_mm"]),
            run_dir=v02_root / "runs" / prompt_id,
            scorer=scorer,
            expected_candidate_count=4,
        )
        replay_rows[prompt_id] = replay
        _write_json(output / "fair_replay" / prompt_id / "ranking.json", replay)
    if sum(row["candidate_count"] for row in replay_rows.values()) != 52:
        raise ValueError("fair replay must load exactly 52 stored v0.2 candidates")

    model_config = _read_json(args.model_config.resolve())
    published_model = published_summary.get("model", {})
    for field in ("model_id", "model_revision"):
        if model_config.get(field) != published_model.get(field):
            raise ValueError(
                f"v0.3 {field} must match published v0.2 model: "
                f"{model_config.get(field)!r} != {published_model.get(field)!r}"
            )
    published_checkpoint = Path(published_model["adapter_checkpoint"]).resolve()
    if args.checkpoint.resolve() != published_checkpoint:
        raise ValueError(
            "v0.3 checkpoint must match published v0.2 checkpoint: "
            f"{args.checkpoint.resolve()} != {published_checkpoint}"
        )
    for prompt_id, replay in replay_rows.items():
        replay_model = replay["model"]
        if any(
            replay_model.get(field) != published_model.get(field)
            for field in ("model_id", "model_revision", "adapter_checkpoint")
        ):
            raise ValueError(f"stored v0.2 model provenance mismatch: {prompt_id}")
    model_provenance = {
        "model_id": model_config["model_id"],
        "model_revision": model_config["model_revision"],
        "adapter_checkpoint": str(args.checkpoint.resolve()),
        "trained_model": True,
        "retrained_for_v0.3": False,
    }
    session = Qwen3PlannerSession(
        checkpoint=args.checkpoint,
        model_id=model_config["model_id"],
        model_revision=model_config["model_revision"],
    )
    generator = ReusingRagGenerator(
        session,
        getattr(args, "reuse_rag_candidates_from", None),
    )
    pipeline = ReferenceGroundedDesignPipeline(
        base_generator=generator,
        provider=reference_provider,
        scorer=scorer,
        model_provenance=model_provenance,
        top_k=args.top_k,
        context_token_budget=args.context_token_budget,
    )
    comparison_rows: list[dict[str, Any]] = []
    for item in benchmark["prompts"]:
        prompt_id = item["id"]
        baseline = replay_rows[prompt_id]
        settings = CandidateGenerationSettings.model_validate(
            baseline["generation_settings"]
        )
        if settings.num_candidates != 4:
            raise ValueError(f"{prompt_id} does not use the required best-of-4 settings")
        run_dir = output / "runs" / prompt_id
        result = pipeline.run(
            prompt=item["prompt"],
            width_mm=float(item["width_mm"]),
            height_mm=float(item["height_mm"]),
            settings=settings,
            run_dir=run_dir,
            raise_on_all_invalid=False,
        )
        rag = _rag_row(result)
        baseline["prompt_tokens"] = rag["baseline_prompt_tokens"]
        row = {
            "prompt_id": prompt_id,
            "category": item["category"],
            "prompt": item["prompt"],
            "same_model_checkpoint": True,
            "same_candidate_count": True,
            "same_generation_settings_and_seeds": True,
            "v0.2": baseline,
            "v0.3": rag,
        }
        comparison_rows.append(row)
        write_manual_review_artifacts(
            prompt_id=prompt_id,
            prompt=item["prompt"],
            v02_preview_path=baseline["winner_preview_path"],
            v02_metrics=baseline["winner_metrics"],
            v03_preview_path=rag["winner_preview_path"],
            v03_metrics=rag["winner_metrics"],
            retrieved_references=_manual_reference_records(
                result.retrieval,
                reference_root=args.reference_index.resolve().parent,
            ),
            output_dir=run_dir,
        )
        _write_json(output / "benchmark_rows.partial.json", comparison_rows)

    summary = summarize_comparison(
        comparison_rows,
        scorer_provenance=scorer.provenance(),
    )
    summary.update(
        {
            "published_v0.2_summary": "v0.2_published_summary.json",
            "published_v0.2_combined_score": published_summary.get(
                "best_of_4_average"
            ),
            "v0.2_source": str(v02_root),
            "reference_index": str(args.reference_index.resolve()),
            "reference_top_k": args.top_k,
            "reference_context_token_budget": args.context_token_budget,
            "model": model_provenance,
            "model_load_seconds": float(session.load_duration_seconds),
            "reused_rag_candidate_count": generator.reuse_hits,
            "rag_reuse_source": (
                str(generator.cache_root) if generator.cache_root is not None else None
            ),
            "human_preference_collected": False,
        }
    )
    _write_json(output / "benchmark_rows.json", comparison_rows)
    _write_json(output / "fair_replay_v0.2.json", list(replay_rows.values()))
    _write_json(output / "benchmark_summary.json", summary)
    return summary


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--reference-index", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--v02-benchmark", type=Path, default=DEFAULT_V02_BENCHMARK)
    parser.add_argument("--model-config", type=Path, default=DEFAULT_MODEL_CONFIG)
    parser.add_argument("--score-config", type=Path, default=DEFAULT_SCORE_CONFIG)
    parser.add_argument(
        "--benchmark-config", type=Path, default=DEFAULT_BENCHMARK_CONFIG
    )
    parser.add_argument("--top-k", type=int, default=5, choices=range(1, 9))
    parser.add_argument("--context-token-budget", type=int, default=350)
    parser.add_argument("--reuse-rag-candidates-from", type=Path)
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.context_token_budget < 128:
        raise ValueError("context-token-budget must be at least 128")
    summary = run_benchmark(args)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["v0.3_complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "load_v03_scorer",
    "replay_v02_prompt",
    "run_benchmark",
    "summarize_comparison",
]
