"""Generate, score, rank, and persist a Qwen3 best-of-N design run."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from training.evaluation.critics import HeuristicAestheticCritic
from training.evaluation.scoring import DesignScorer, ScoreWeights
from training.inference.candidates import BestOfNSelector, CandidateGenerationSettings
from training.inference.qwen3_planner import Qwen3PlannerSession
from training.preference.builder import export_preference


def _load_weights(path: Path) -> ScoreWeights:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return ScoreWeights.model_validate(payload["weights"])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--model-config", type=Path, required=True)
    parser.add_argument(
        "--score-config",
        type=Path,
        default=Path("training/config/scoring/aesthetic_v0_2.json"),
    )
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--width-mm", type=float, required=True)
    parser.add_argument("--height-mm", type=float, required=True)
    parser.add_argument("--num-candidates", type=int, default=4)
    parser.add_argument("--base-seed", type=int, default=42)
    parser.add_argument("--max-new-tokens", type=int, default=768)
    parser.add_argument("--temperature", type=float, default=0.7)
    parser.add_argument("--top-p", type=float, default=0.8)
    parser.add_argument("--top-k", type=int, default=20)
    parser.add_argument("--repetition-penalty", type=float, default=1.05)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    model_config = json.loads(args.model_config.read_text(encoding="utf-8"))
    session = Qwen3PlannerSession(
        checkpoint=args.checkpoint,
        model_id=model_config["model_id"],
        model_revision=model_config["model_revision"],
    )
    model_provenance = {
        "generator": "qwen3_1_7b_local_qlora_v0.2",
        "model_id": model_config["model_id"],
        "model_revision": model_config["model_revision"],
        "adapter_checkpoint": str(args.checkpoint.resolve()),
        "trained_model": True,
    }
    scorer = DesignScorer(
        weights=_load_weights(args.score_config),
        aesthetic_critic=HeuristicAestheticCritic(),
    )
    settings = CandidateGenerationSettings(
        num_candidates=args.num_candidates,
        base_seed=args.base_seed,
        max_new_tokens=args.max_new_tokens,
        temperature=args.temperature,
        top_p=args.top_p,
        top_k=args.top_k,
        repetition_penalty=args.repetition_penalty,
    )
    result = BestOfNSelector(
        generator=session,
        scorer=scorer,
        model_provenance=model_provenance,
    ).run(
        prompt=args.prompt,
        width_mm=args.width_mm,
        height_mm=args.height_mm,
        settings=settings,
        run_dir=args.output,
    )
    durations = [
        float(record.generation["duration_seconds"])
        for record in result.candidates.values()
    ]
    peak_vram = max(
        float(record.generation["peak_vram_gib"])
        for record in result.candidates.values()
    )
    performance = {
        "model_load_seconds": session.load_duration_seconds,
        "total_candidate_generation_seconds": sum(durations),
        "average_candidate_generation_seconds": sum(durations) / len(durations),
        "peak_vram_gib": peak_vram,
    }
    (result.run_dir / "performance.json").write_text(
        json.dumps(performance, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    preference = None
    if len(result.candidates) >= 2:
        preference = export_preference(
            result.run_dir,
            result.run_dir / "preference.auto.json",
        )
    output = {
        "status": "success",
        "winner": result.ranking.winner,
        "ranking": result.ranking.model_dump(mode="json"),
        "diversity": result.diversity,
        "performance": performance,
        "run_dir": str(result.run_dir),
        "contact_sheet": str(result.contact_sheet),
        "comparison_report": str(result.comparison_report),
        "preference": str(preference) if preference else None,
    }
    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
