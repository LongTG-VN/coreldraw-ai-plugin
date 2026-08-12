from __future__ import annotations

import json
from pathlib import Path

import pytest

from training.evaluation.critics import HeuristicAestheticCritic
from training.evaluation.scoring import DesignScorer, ScoreWeights
from training.inference.baseline import generate_baseline_design
from training.inference.preview import render_preview
from training.tools.benchmark_reference_rag import (
    _parser,
    replay_v02_prompt,
    summarize_comparison,
)


def _scorer() -> DesignScorer:
    return DesignScorer(
        weights=ScoreWeights(
            technical=0.25,
            composition=0.15,
            visual_hierarchy=0.15,
            typography=0.10,
            spacing=0.10,
            color_harmony=0.08,
            balance=0.05,
            readability=0.10,
            prompt_match=0.02,
        ),
        aesthetic_critic=HeuristicAestheticCritic(),
    )


def test_visual_benchmark_mode_is_explicit_and_fresh_by_default() -> None:
    args = _parser().parse_args(
        [
            "--checkpoint",
            "checkpoint-5",
            "--reference-index",
            "reference_index.jsonl",
            "--output",
            "benchmark-output",
            "--visual-composition",
        ]
    )

    assert args.visual_composition is True
    assert args.resume is False
    assert args.audited_rag_cache_from is None
    assert args.reuse_rag_candidates_from is None


def _stored_run(tmp_path: Path, *, count: int = 2) -> Path:
    run_dir = tmp_path / "v02" / "runs" / "spa"
    candidates = run_dir / "candidates"
    candidates.mkdir(parents=True)
    request = {
        "prompt": "Poster spa",
        "width_mm": 100,
        "height_mm": 50,
        "generation": {
            "num_candidates": count,
            "base_seed": 40,
            "max_new_tokens": 128,
            "do_sample": True,
            "temperature": 0.7,
            "top_p": 0.8,
            "top_k": 20,
            "repetition_penalty": 1.05,
        },
        "model": {
            "model_id": "Qwen/Qwen3-1.7B",
            "model_revision": "fixture",
            "adapter_checkpoint": "fixture/checkpoint-5",
        },
    }
    (run_dir / "request.json").write_text(json.dumps(request), encoding="utf-8")
    for index in range(count):
        candidate_dir = candidates / f"candidate_{index + 1:02d}"
        candidate_dir.mkdir()
        document = generate_baseline_design("Poster spa", 100, 50)
        payload = document.model_dump(mode="json")
        payload["elements"][1]["bbox"]["x"] += index * 4
        payload["elements"][1]["bbox_norm"]["x"] += index * 0.04
        (candidate_dir / "design.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )
        render_preview(
            type(document).model_validate(payload), candidate_dir / "preview.png"
        )
        (candidate_dir / "validation.json").write_text(
            json.dumps(
                {
                    "strict_schema_valid": True,
                    "raw_schema_valid": True,
                    "recovery_steps": [],
                }
            ),
            encoding="utf-8",
        )
        (candidate_dir / "generation.json").write_text(
            json.dumps(
                {
                    "seed": 40 + index,
                    "duration_seconds": 1 + index,
                    "peak_vram_gib": 1.2 + index * 0.1,
                }
            ),
            encoding="utf-8",
        )
    return run_dir


def test_fair_replay_rescores_every_stored_candidate(tmp_path: Path) -> None:
    replay = replay_v02_prompt(
        prompt_id="spa",
        prompt="Poster spa",
        width_mm=100,
        height_mm=50,
        run_dir=_stored_run(tmp_path),
        scorer=_scorer(),
        expected_candidate_count=2,
    )

    assert replay["comparison_basis"] == "fair_replay_with_v0.3_scorer"
    assert replay["candidate_count"] == 2
    assert replay["valid_candidate_count"] == 2
    assert replay["candidate_validity_rate"] == 1
    assert len(replay["ranking"]["candidates"]) == 2
    assert replay["winner_metrics"]["schema_valid"] is True
    assert replay["generation_settings"]["base_seed"] == 40
    assert replay["average_candidate_generation_seconds"] == 1.5


def test_fair_replay_rejects_prompt_or_candidate_mismatch(tmp_path: Path) -> None:
    run_dir = _stored_run(tmp_path)
    with pytest.raises(ValueError, match="request mismatch"):
        replay_v02_prompt(
            prompt_id="spa",
            prompt="Different",
            width_mm=100,
            height_mm=50,
            run_dir=run_dir,
            scorer=_scorer(),
            expected_candidate_count=2,
        )
    with pytest.raises(ValueError, match="must contain 4"):
        replay_v02_prompt(
            prompt_id="spa",
            prompt="Poster spa",
            width_mm=100,
            height_mm=50,
            run_dir=run_dir,
            scorer=_scorer(),
            expected_candidate_count=4,
        )


def _version(
    *,
    score: float,
    overlap: float,
    hierarchy: float,
    text_fit: float,
) -> dict:
    return {
        "winner_metrics": {
            "combined_score": score,
            "technical_score": 0.8,
            "overlap": overlap,
            "spacing": 0.8,
            "hierarchy": hierarchy,
            "text_fit": text_fit,
            "coverage": 0.5,
            "outside_canvas": 0.0,
        },
        "candidate_validity_rate": 1.0,
        "candidate_diversity": 0.3,
        "average_candidate_generation_seconds": 2.0,
        "total_candidate_generation_seconds": 8.0,
        "peak_vram_gib": 1.4,
        "severe_outside_candidate_count": 0,
    }


def test_summary_enforces_every_success_gate() -> None:
    v02 = _version(score=0.5, overlap=0.10, hierarchy=0.70, text_fit=0.50)
    v02["prompt_tokens"] = 100
    v03 = {
        **_version(score=0.55, overlap=0.105, hierarchy=0.71, text_fit=0.60),
        "retrieval_latency_seconds": 0.01,
        "baseline_prompt_tokens": 100,
        "rag_prompt_tokens": 300,
        "reference_prompt_token_delta": 200,
        "reference_context_estimated_tokens": 180,
        "retrieval": {
            "relevance": 0.9,
            "diversity": 0.8,
            "category_accuracy": 1.0,
            "format_match": 1.0,
            "style_relevance": 0.7,
        },
    }
    summary = summarize_comparison(
        [{"v0.2": v02, "v0.3": v03}], scorer_provenance={"technical": "v0.3"}
    )

    assert summary["combined_score_improvement_percent"] == pytest.approx(10)
    assert all(summary["success_gates"].values())
    assert summary["v0.3_complete"] is True

    failed = {**v03, "winner_metrics": {**v03["winner_metrics"], "hierarchy": 0.69}}
    summary = summarize_comparison(
        [{"v0.2": v02, "v0.3": failed}], scorer_provenance={}
    )
    assert summary["success_gates"]["hierarchy_not_worse_than_v0.2"] is False
    assert summary["v0.3_complete"] is False
