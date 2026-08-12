"""Run one local Qwen3 reference-grounded best-of-N design request."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from training.evaluation.critics import HeuristicAestheticCritic
from training.evaluation.scoring import DesignScorer, ScoreWeights
from training.inference.candidates import CandidateGenerationSettings
from training.inference.qwen3_planner import Qwen3PlannerSession
from training.inference.rag import ReferenceGroundedDesignPipeline
from training.retrieval import JsonlReferenceProvider


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument(
        "--model-config",
        type=Path,
        default=Path("training/config/experiments/qwen3_1_7b_local_qlora.json"),
    )
    parser.add_argument(
        "--score-config",
        type=Path,
        default=Path("training/config/scoring/aesthetic_v0_3.json"),
    )
    parser.add_argument("--reference-index", type=Path, required=True)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--width-mm", type=float, required=True)
    parser.add_argument("--height-mm", type=float, required=True)
    parser.add_argument("--num-candidates", type=int, default=4)
    parser.add_argument("--reference-top-k", type=int, default=5)
    parser.add_argument("--reference-token-budget", type=int, default=350)
    parser.add_argument("--base-seed", type=int, default=42)
    parser.add_argument("--max-new-tokens", type=int, default=768)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    model = _load_json(args.model_config)
    weights = ScoreWeights.model_validate(_load_json(args.score_config)["weights"])
    session = Qwen3PlannerSession(
        checkpoint=args.checkpoint,
        model_id=model["model_id"],
        model_revision=model["model_revision"],
    )
    provenance = {
        "model_id": model["model_id"],
        "model_revision": model["model_revision"],
        "adapter_checkpoint": str(args.checkpoint.resolve()),
        "trained_model": True,
        "quantization": "NF4 4-bit",
        "lora_rank": model["lora"]["rank"],
        "lora_alpha": model["lora"]["alpha"],
    }
    pipeline = ReferenceGroundedDesignPipeline(
        base_generator=session,
        provider=JsonlReferenceProvider(args.reference_index),
        scorer=DesignScorer(
            weights=weights,
            aesthetic_critic=HeuristicAestheticCritic(),
        ),
        model_provenance=provenance,
        top_k=args.reference_top_k,
        context_token_budget=args.reference_token_budget,
    )
    result = pipeline.run(
        prompt=args.prompt,
        width_mm=args.width_mm,
        height_mm=args.height_mm,
        settings=CandidateGenerationSettings(
            num_candidates=args.num_candidates,
            base_seed=args.base_seed,
            max_new_tokens=args.max_new_tokens,
        ),
        run_dir=args.output,
    )
    performance = _load_json(args.output / "performance.json")
    performance["model_load_seconds"] = session.load_duration_seconds
    (args.output / "performance.json").write_text(
        json.dumps(performance, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": "success",
                "winner": result.selection.ranking.winner,
                "references": [item.reference_id for item in result.retrieval],
                "ranking": result.selection.ranking.model_dump(mode="json"),
                "performance": performance,
                "run_dir": str(result.selection.run_dir),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
