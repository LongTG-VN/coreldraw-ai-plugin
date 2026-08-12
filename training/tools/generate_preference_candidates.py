"""Generate fresh, identity-recorded Qwen candidates for the v0.4 review pool."""

from __future__ import annotations

import argparse
import gc
import json
import time
from pathlib import Path

from training.inference.candidates import CandidateGenerationSettings
from training.inference.qwen3_planner import Qwen3PlannerSession
from training.inference.rag import ReferenceGroundedDesignPipeline
from training.retrieval import JsonlReferenceProvider
from training.tools._benchmark_reference_rag_impl import AuditedRagGenerator, load_v03_scorer
from training.visual import apply_aesthetic_hardening


def _read(path: Path) -> dict:
    return json.loads(path.resolve().read_text(encoding="utf-8"))


def _complete_run(path: Path, *, expected_candidates: int) -> bool:
    candidates = path / "candidates"
    if not candidates.is_dir() or len(list(candidates.glob("candidate_*"))) != expected_candidates:
        return False
    return all(
        (candidate / "generation.json").is_file()
        and (candidate / "validation.json").is_file()
        for candidate in candidates.glob("candidate_*")
    )


def generate(args: argparse.Namespace) -> dict:
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    config = _read(args.briefs)
    model = _read(args.model_config)
    checkpoint = args.checkpoint.resolve()
    provider = JsonlReferenceProvider(args.reference_index.resolve())
    scorer = load_v03_scorer(args.score_config)
    started = time.perf_counter()
    session = Qwen3PlannerSession(
        checkpoint=checkpoint,
        model_id=model["model_id"],
        model_revision=model["model_revision"],
    )
    generator = AuditedRagGenerator(
        session,
        model_id=model["model_id"],
        model_revision=model["model_revision"],
        checkpoint=checkpoint,
    )

    def harden(document, brief):
        hardened, report = apply_aesthetic_hardening(document, brief=brief)
        return hardened, {
            "engine": "v0.3.2_aesthetic_hardening",
            "hardening": report,
            "v0.3.3_assets_applied_when_manifest_available": False,
        }

    pipeline = ReferenceGroundedDesignPipeline(
        base_generator=generator,
        provider=provider,
        scorer=scorer,
        model_provenance={
            "model_id": model["model_id"],
            "model_revision": model["model_revision"],
            "adapter_checkpoint": str(checkpoint),
            "trained_model": True,
            "retrained_for_v0.4": False,
            "failed_visual_rag_enabled": False,
            "failed_vision_critic_enabled": False,
        },
        top_k=5,
        context_token_budget=350,
        visual_composition=True,
        benchmark_mode=True,
        document_postprocessor=harden,
    )
    rows = []
    peak_vram = 0.0
    fresh_before = generator.fresh_generation_count
    for brief in config["briefs"]:
        candidate_count = int(brief.get("num_candidates", 4))
        run_dir = output / "runs" / brief["id"]
        if run_dir.exists():
            if not _complete_run(run_dir, expected_candidates=candidate_count):
                raise ValueError(f"partial run requires manual audit, refusing overwrite: {run_dir}")
            rows.append({"brief_id": brief["id"], "status": "existing_complete", "candidate_count": candidate_count})
            continue
        result = pipeline.run(
            prompt=brief["prompt"],
            width_mm=float(brief["width_mm"]),
            height_mm=float(brief["height_mm"]),
            settings=CandidateGenerationSettings(
                num_candidates=candidate_count,
                base_seed=int(brief["seed"]),
                max_new_tokens=int(brief.get("max_new_tokens", 512)),
                do_sample=True,
                temperature=.7,
                top_p=.8,
                top_k=20,
                repetition_penalty=1.05,
            ),
            run_dir=run_dir,
            raise_on_all_invalid=False,
        )
        valid = sum(record.document is not None and record.score.eligible for record in result.selection.candidates.values())
        peak_vram = max(peak_vram, *(record.generation.get("peak_vram_gib", 0) for record in result.selection.candidates.values()))
        rows.append({
            "brief_id": brief["id"], "status": "fresh", "candidate_count": candidate_count,
            "technically_eligible_count": valid,
            "candidate_diversity": result.selection.diversity,
        })
    summary = {
        "schema_version": "1.0",
        "brief_count": len(config["briefs"]),
        "candidate_count": sum(int(item.get("num_candidates", 4)) for item in config["briefs"]),
        "fresh_candidate_count": generator.fresh_generation_count - fresh_before,
        "unsafe_reused_candidate_count": 0,
        "benchmark_sample_data": config["benchmark_sample_data"],
        "customer_provided": config["customer_provided"],
        "model": model["model_id"],
        "model_revision": model["model_revision"],
        "checkpoint": str(checkpoint),
        "model_load_seconds": session.load_duration_seconds,
        "peak_vram_gib": peak_vram,
        "duration_seconds": time.perf_counter() - started,
        "rows": rows,
        "human_labels_collected": 0,
    }
    (output / "generation_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    del pipeline, generator, session
    gc.collect()
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--briefs", type=Path, default=Path("training/config/preference/v0_4_phase1_additional_briefs.json"))
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--reference-index", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model-config", type=Path, default=Path("training/config/experiments/qwen3_1_7b_local_qlora.json"))
    parser.add_argument("--score-config", type=Path, default=Path("training/config/scoring/aesthetic_v0_3.json"))
    args = parser.parse_args()
    print(json.dumps(generate(args), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
