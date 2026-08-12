"""Run ten fresh Qwen generations through the v0.3.3 asset-aware pipeline."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from statistics import mean
from typing import Any

from training.evaluation.critics import HeuristicAestheticCritic
from training.evaluation.scoring import DesignScorer, ScoreWeights
from training.inference.candidates import CandidateGenerationSettings
from training.inference.qwen3_planner import Qwen3PlannerSession
from training.inference.rag import ReferenceGroundedDesignPipeline
from training.retrieval import JsonlReferenceProvider, StructuredBriefV1
from training.tools.replay_asset_aware_composition import (
    CASE_TO_PROMPT,
    _prepare_case_document,
)
from training.visual.asset_aware import apply_asset_aware_composition
from training.visual.asset_contracts import AssetManifestV1
from training.visual.hardening import apply_aesthetic_hardening


MODEL_ID = "Qwen/Qwen3-1.7B"
MODEL_REVISION = "70d244cc86ccca08cf5af4e1e306ecf908b1ad5e"


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _prompt(case: dict[str, Any], manifest: AssetManifestV1) -> str:
    fields = {
        key: value
        for key, value in case.items()
        if key in {"headline", "subheadline", "body", "cta", "offer", "items"}
    }
    assets = [
        {
            "role": asset.role,
            "aspect_ratio": asset.aspect_ratio,
            "fit_mode": asset.fit_mode,
            "source_type": asset.source_type,
        }
        for asset in manifest.assets
    ]
    return (
        "Create an editable Vietnamese design for this exact benchmark brief. "
        "Preserve the supplied copy; do not invent customer data. Actual licensed or "
        "project-owned assets are available and will be bound deterministically after "
        "planning, so reserve suitable logo/hero/product regions. "
        f"CASE={case['case_id']}. COPY={json.dumps(fields, ensure_ascii=False)}. "
        f"ASSET_GEOMETRY={json.dumps(assets, ensure_ascii=False)}. "
        f"BENCHMARK_SAMPLE_DATA={bool(case['benchmark_sample_data'])}."
    )


def run(
    *,
    checkpoint: Path,
    reference_index: Path,
    asset_root: Path,
    metadata_source: Path,
    output: Path,
    model_config_path: Path,
    score_config_path: Path,
) -> dict[str, Any]:
    paths = [checkpoint, reference_index, asset_root, metadata_source]
    if any(not path.exists() for path in paths):
        missing = [str(path) for path in paths if not path.exists()]
        raise FileNotFoundError(f"required smoke inputs missing: {missing}")
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"output must be new or empty: {output}")
    output.mkdir(parents=True, exist_ok=True)
    runs = output / "runs"
    runs.mkdir()
    model_config = _read_json(model_config_path)
    if model_config["model_id"] != MODEL_ID:
        raise ValueError("unexpected model ID")
    if model_config["model_revision"] != MODEL_REVISION:
        raise ValueError("unexpected model revision")
    score_config = _read_json(score_config_path)
    scorer = DesignScorer(
        weights=ScoreWeights.model_validate(score_config["weights"]),
        aesthetic_critic=HeuristicAestheticCritic(),
    )
    session = Qwen3PlannerSession(
        checkpoint=checkpoint,
        model_id=MODEL_ID,
        model_revision=MODEL_REVISION,
    )
    provider = JsonlReferenceProvider(reference_index)
    rows: list[dict[str, Any]] = []
    for index, (case_id, prompt_id) in enumerate(CASE_TO_PROMPT.items()):
        case_dir = asset_root / case_id
        case = _read_json(case_dir / "case.json")
        manifest = AssetManifestV1.model_validate(
            _read_json(case_dir / "asset_manifest.json")
        )
        source_request = _read_json(metadata_source / "runs" / prompt_id / "request.json")

        def postprocess(
            document: Any,
            brief: StructuredBriefV1,
            *,
            benchmark_case: dict[str, Any] = case,
            benchmark_case_id: str = case_id,
            asset_manifest: AssetManifestV1 = manifest,
            base_dir: Path = case_dir,
        ) -> tuple[Any, dict[str, object]]:
            prepared = _prepare_case_document(
                document,
                case_id=benchmark_case_id,
                case=benchmark_case,
            )
            hardened, hardening_report = apply_aesthetic_hardening(
                prepared,
                brief=brief,
            )
            aware, asset_report = apply_asset_aware_composition(
                hardened,
                brief=brief,
                manifest=asset_manifest,
                base_dir=base_dir,
            )
            return aware, {
                "engine": "v0.3.2_hardening_plus_v0.3.3_asset_aware",
                "hardening": hardening_report,
                "asset_aware": asset_report,
            }

        pipeline = ReferenceGroundedDesignPipeline(
            base_generator=session,
            provider=provider,
            scorer=scorer,
            model_provenance={
                "model_id": MODEL_ID,
                "model_revision": MODEL_REVISION,
                "adapter_checkpoint": str(checkpoint.resolve()),
                "trained_model": True,
                "quantization": "NF4 4-bit",
                "retrained_for_v0.3.3": False,
            },
            top_k=5,
            context_token_budget=350,
            visual_composition=True,
            benchmark_mode=True,
            document_postprocessor=postprocess,
        )
        run_dir = runs / case_id
        result = pipeline.run(
            prompt=_prompt(case, manifest),
            width_mm=float(source_request["width_mm"]),
            height_mm=float(source_request["height_mm"]),
            settings=CandidateGenerationSettings(
                num_candidates=2,
                base_seed=3300 + index * 10,
                max_new_tokens=512,
            ),
            run_dir=run_dir,
            raise_on_all_invalid=False,
        )
        shutil.copy2(case_dir / "case.json", run_dir / "case.json")
        shutil.copy2(case_dir / "asset_manifest.json", run_dir / "asset_manifest.json")
        candidate_rows = []
        for candidate_id, record in result.selection.candidates.items():
            candidate_rows.append(
                {
                    "candidate_id": candidate_id,
                    "fresh_generation": True,
                    "schema_valid": bool(record.validation.get("strict_schema_valid")),
                    "eligible": record.score.eligible,
                    "duration_seconds": float(record.generation["duration_seconds"]),
                    "peak_vram_gib": float(record.generation["peak_vram_gib"]),
                }
            )
        rows.append(
            {
                "case_id": case_id,
                "winner": result.selection.ranking.winner,
                "candidate_count": len(candidate_rows),
                "candidates": candidate_rows,
                "retrieved_reference_ids": [item.reference_id for item in result.retrieval],
                "retrieval_latency_seconds": result.retrieval_latency_seconds,
            }
        )
        _write_json(output / "summary.partial.json", {"rows": rows})
    candidates = [candidate for row in rows for candidate in row["candidates"]]
    summary = {
        "schema_version": "1.0",
        "artifact_type": "design_ai_v0.3.3_fresh_asset_smoke",
        "model_id": MODEL_ID,
        "model_revision": MODEL_REVISION,
        "checkpoint": str(checkpoint.resolve()),
        "retrained": False,
        "unsafe_cache_reuse_count": 0,
        "fresh_candidate_count": len(candidates),
        "expected_fresh_candidate_count": 10,
        "schema_valid_candidate_count": sum(item["schema_valid"] for item in candidates),
        "eligible_candidate_count": sum(item["eligible"] for item in candidates),
        "average_candidate_latency_seconds": mean(
            item["duration_seconds"] for item in candidates
        ),
        "peak_vram_gib": max(item["peak_vram_gib"] for item in candidates),
        "model_load_seconds": float(session.load_duration_seconds),
        "rows": rows,
    }
    _write_json(output / "summary.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--reference-index", type=Path, required=True)
    parser.add_argument("--asset-root", type=Path, required=True)
    parser.add_argument("--metadata-source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
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
    args = parser.parse_args()
    summary = run(
        checkpoint=args.checkpoint.resolve(),
        reference_index=args.reference_index.resolve(),
        asset_root=args.asset_root.resolve(),
        metadata_source=args.metadata_source.resolve(),
        output=args.output.resolve(),
        model_config_path=args.model_config.resolve(),
        score_config_path=args.score_config.resolve(),
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["fresh_candidate_count"] == 10 else 2


if __name__ == "__main__":
    raise SystemExit(main())
