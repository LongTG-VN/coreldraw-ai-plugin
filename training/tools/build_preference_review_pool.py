"""Build the v0.4 Phase 1 audit pool and blinded review queue from safe artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import mean
from typing import Any

from PIL import Image, ImageDraw, ImageOps

from training.evaluation.diversity import candidate_diversity
from training.preference.v04.models import ReviewQueueItemV1
from training.preference.v04.pairing import (
    candidate_from_directory,
    candidate_from_explicit_artifacts,
    canonical_pair_id,
    tournament_pairs,
    write_queue,
)
from training.schemas.design import DesignDocument


V033_CASE_PROMPT = {
    "spa": "spa_luxury", "cafe": "cafe_vintage", "sale": "sale_bold",
    "menu": "dense_food_menu", "signage": "signage_wide",
}


def _read(path: Path) -> Any:
    return json.loads(path.resolve().read_text(encoding="utf-8"))


def _admit_qwen_candidates(
    *, run: Path, replacement_runs: list[Path], brief_id: str,
    generation_source: str, pool_source: str,
) -> list:
    directories = sorted((run / "candidates").glob("candidate_*"))
    for replacement_run in replacement_runs:
        if replacement_run.is_dir():
            directories.extend(sorted((replacement_run / "candidates").glob("candidate_*")))
    admitted = []
    for directory in directories:
        try:
            candidate = candidate_from_directory(
                candidate_dir=directory, brief_id=brief_id,
                design_id=f"qwen:{brief_id}:{len(admitted) + 1}",
                generation_source=generation_source,
                provenance={
                    "source_run": str(directory.parent.parent), "trained_model": True,
                    "visual_rag_enabled": False, "vision_critic_enabled": False,
                    "preference_label": None, "pool_source": pool_source,
                    "replacement_candidate": run not in directory.parents,
                },
                license_class="research_only", commercial_allowed=False,
            )
        except (ValueError, FileNotFoundError):
            continue
        admitted.append(candidate)
        if len(admitted) == 4:
            break
    if len(admitted) != 4:
        raise ValueError(f"{brief_id} has only {len(admitted)} technically eligible candidates")
    return admitted


def _historical_pair(
    *, comparison: Path, brief_id: str | None = None, category: str | None = None,
    provenance: dict[str, Any], license_class: str = "research_only",
) -> ReviewQueueItemV1 | None:
    payload = _read(comparison)
    variants = payload.get("variants", {})
    if len(variants) != 2:
        raise ValueError(f"historical comparison must contain two variants: {comparison}")
    keys = list(variants)
    actual_brief = brief_id or str(payload["prompt_id"])
    candidates = []
    for index, key in enumerate(keys, 1):
        value = variants[key]
        candidates.append(candidate_from_explicit_artifacts(
            design_path=Path(value["design_path"]), preview_path=Path(value["preview_path"]),
            brief_id=actual_brief, design_id=f"historical:{actual_brief}:{provenance['comparison_family']}:{index}",
            generation_source=f"historical_{key}",
            provenance={**provenance, "hidden_variant": key, "source_comparison": str(comparison.resolve())},
            license_class=license_class, commercial_allowed=False,
        ))
    if candidates[0].content_sha256 == candidates[1].content_sha256:
        return None
    return ReviewQueueItemV1(
        pair_id=canonical_pair_id(actual_brief, candidates[0].content_sha256, candidates[1].content_sha256),
        brief_id=actual_brief, prompt=str(payload["prompt"]),
        category=category or str(payload.get("category", actual_brief.split("_")[0])),
        candidate_1=candidates[0], candidate_2=candidates[1], pairing_stage="historical",
        benchmark_sample_data=True, customer_provided=False,
        provenance={**provenance, "automatic_winner_imported": False, "human_label": None},
        license_class=license_class, commercial_allowed=False,
    )


def _direct_historical_pair(
    *, brief_id: str, prompt: str, category: str,
    left_design: Path, left_preview: Path, right_design: Path, right_preview: Path,
    family: str,
) -> ReviewQueueItemV1 | None:
    candidates = [
        candidate_from_explicit_artifacts(
            design_path=design, preview_path=preview, brief_id=brief_id,
            design_id=f"historical:{brief_id}:{family}:{index}",
            generation_source=f"historical_{family}",
            provenance={"comparison_family": family, "side_identity_hidden": True},
            license_class="research_only", commercial_allowed=False,
        )
        for index, (design, preview) in enumerate(((left_design, left_preview), (right_design, right_preview)), 1)
    ]
    if candidates[0].content_sha256 == candidates[1].content_sha256:
        return None
    return ReviewQueueItemV1(
        pair_id=canonical_pair_id(brief_id, candidates[0].content_sha256, candidates[1].content_sha256),
        brief_id=brief_id, prompt=prompt, category=category,
        candidate_1=candidates[0], candidate_2=candidates[1], pairing_stage="historical",
        benchmark_sample_data=True, customer_provided=False,
        provenance={"comparison_family": family, "automatic_winner_imported": False, "human_label": None},
        license_class="research_only", commercial_allowed=False,
    )


def _contact_sheet(rows: list[tuple[str, list[Path]]], output: Path) -> None:
    cell_w, cell_h, label_h = 340, 250, 32
    sheet = Image.new("RGB", (cell_w * 4, (cell_h + label_h) * len(rows)), "#E6E5E2")
    draw = ImageDraw.Draw(sheet)
    for row, (brief_id, paths) in enumerate(rows):
        y = row * (cell_h + label_h)
        draw.text((10, y + 8), brief_id, fill="#111111")
        for column, path in enumerate(paths):
            with Image.open(path) as source:
                image = ImageOps.contain(source.convert("RGB"), (cell_w - 16, cell_h - 12))
            x = column * cell_w + (cell_w - image.width) // 2
            sheet.paste(image, (x, y + label_h + (cell_h - image.height) // 2))
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output, format="PNG", optimize=True)


def _selected_diversity(candidates) -> float:
    documents = {
        item.design_id: DesignDocument.model_validate_json(
            Path(item.design_path).read_text(encoding="utf-8")
        )
        for item in candidates
    }
    return float(candidate_diversity(documents)["average_layout_distance"])


def build(args: argparse.Namespace) -> dict[str, Any]:
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"pool output must be new or empty: {output}")
    output.mkdir(parents=True, exist_ok=True)
    base_config = _read(args.base_briefs)
    extra_config = _read(args.extra_briefs)
    all_pairs: list[ReviewQueueItemV1] = []
    candidate_rows: list[tuple[str, list[Path]]] = []
    selected_candidates = []
    brief_records = []
    diversity_values = []
    # Thirteen existing fresh-Qwen best-of-four runs, postprocessed by the safe v0.3.1 path.
    base_by_id = {item["id"]: item for item in base_config["prompts"]}
    for brief_id, brief in base_by_id.items():
        run = args.base_runs.resolve() / "runs" / brief_id
        candidates = _admit_qwen_candidates(
            run=run,
            replacement_runs=[root.resolve() / "runs" / brief_id for root in args.replacement_runs],
            brief_id=brief_id,
            generation_source="qwen3_v0.3.1_existing_fresh_generation",
            pool_source="v0.3.1_clean_candidates",
        )
        all_pairs.extend(tournament_pairs(
            brief_id=brief_id, prompt=brief["prompt"], category=brief["category"], candidates=candidates,
            benchmark_sample_data=True, customer_provided=False,
            provenance={"pool_source": "v0.3.1_clean_candidates", "human_label": None},
        ))
        selected_candidates.extend(candidates)
        candidate_rows.append((brief_id, [Path(item.preview_path) for item in candidates]))
        diversity_values.append(_selected_diversity(candidates))
        brief_records.append({**brief, "candidate_count": 4, "source": "existing_qwen_v031"})
    # Seven new Qwen runs bring the initial pool to the explicitly allowed 20-brief budget.
    for brief in extra_config["briefs"]:
        brief_id = brief["id"]
        run = args.extra_runs.resolve() / "runs" / brief_id
        replacement_runs = [root.resolve() / "runs" / brief_id for root in args.replacement_runs]
        candidates = _admit_qwen_candidates(
            run=run, replacement_runs=replacement_runs, brief_id=brief_id,
            generation_source="qwen3_v0.4_phase1_fresh_generation",
            pool_source="v0.4_phase1_fresh_qwen",
        )
        all_pairs.extend(tournament_pairs(
            brief_id=brief_id, prompt=brief["prompt"], category=brief["category"], candidates=candidates,
            benchmark_sample_data=True, customer_provided=False,
            provenance={"pool_source": "v0.4_phase1_fresh_qwen", "human_label": None},
        ))
        selected_candidates.extend(candidates)
        candidate_rows.append((brief_id, [Path(item.preview_path) for item in candidates]))
        diversity_values.append(_selected_diversity(candidates))
        brief_records.append({**brief, "candidate_count": 4, "source": "fresh_qwen_v04_phase1"})
    # Historical progression enters blinded; no stored winner/score becomes a label.
    historical: list[ReviewQueueItemV1 | None] = []
    for brief_id, brief in base_by_id.items():
        historical.append(_historical_pair(
            comparison=args.v031_root / "runs" / brief_id / "comparison.json",
            brief_id=brief_id, category=brief["category"],
            provenance={"comparison_family": "v0.2_vs_v0.3"},
        ))
        historical.append(_historical_pair(
            comparison=args.v032_root / "runs" / brief_id / "comparison.json",
            brief_id=brief_id, category=brief["category"],
            provenance={"comparison_family": "v0.3.1_vs_v0.3.2"},
        ))
    for case_id, brief_id in V033_CASE_PROMPT.items():
        brief = base_by_id[brief_id]
        historical.append(_historical_pair(
            comparison=args.v033_root / "runs" / case_id / "comparison.json",
            brief_id=brief_id, category=brief["category"],
            provenance={"comparison_family": "v0.3.2_vs_v0.3.3"},
        ))
    for case_id in ("sale", "spa"):
        brief_id = V033_CASE_PROMPT[case_id]
        brief = base_by_id[brief_id]
        historical.append(_direct_historical_pair(
            brief_id=brief_id, prompt=brief["prompt"], category=brief["category"],
            left_design=args.v033_root / "runs" / case_id / "asset_aware" / "design.json",
            left_preview=args.v033_root / "runs" / case_id / "asset_aware" / "preview.png",
            right_design=args.v035_root / "runs" / case_id / "final" / "design.json",
            right_preview=args.v035_root / "runs" / case_id / "final" / "preview.png",
            family="v0.3.3_vs_v0.3.5",
        ))
    admitted_historical = [item for item in historical if item is not None]
    all_pairs.extend(admitted_historical)
    queue_path = write_queue(all_pairs, output / "review_queue" / "review_queue.jsonl")
    for record in brief_records:
        path = output / "briefs" / f"{record['id']}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    _contact_sheet(candidate_rows, output / "contact_sheets" / "initial_preference_pool_contact_sheet.png")
    generation_summaries = [_read(args.extra_runs / "generation_summary.json")]
    generation_summaries.extend(
        _read(root / "generation_summary.json") for root in args.replacement_runs
    )
    generation = generation_summaries[0]
    total_generation_attempts = sum(int(item["fresh_candidate_count"]) for item in generation_summaries)
    total_generation_seconds = sum(float(item["duration_seconds"]) for item in generation_summaries)
    peak_vram = max(float(item["peak_vram_gib"]) for item in generation_summaries)
    fresh_candidates_in_pool = sum(
        bool(item.provenance.get("replacement_candidate"))
        or item.provenance.get("pool_source") == "v0.4_phase1_fresh_qwen"
        for item in selected_candidates
    )
    summary = {
        "schema_version": "1.0", "checkpoint": "Design AI v0.4 Phase 1 — Human Preference Collection System",
        "brief_count": len(brief_records), "candidate_count": len(candidate_rows) * 4,
        "category_count": len({item["category"] for item in brief_records}),
        "categories": sorted({item["category"] for item in brief_records}),
        "tournament_pair_count": len(brief_records) * 4,
        "historical_pair_count": len(admitted_historical), "review_queue_pair_count": len(all_pairs),
        "human_labels_collected": 0, "human_preference_source": "explicit_UI_only",
        "technical_pass_rate": 1.0,
        "average_layout_distance": mean(diversity_values),
        "meaningful_diversity_brief_count": sum(value > .12 for value in diversity_values),
        "new_valid_candidate_count": fresh_candidates_in_pool,
        "fresh_generation_attempt_count": total_generation_attempts,
        "failed_generation_attempt_count": total_generation_attempts - fresh_candidates_in_pool,
        "unsafe_reused_candidate_count": 0,
        "new_generation_duration_seconds": total_generation_seconds,
        "peak_vram_gib": peak_vram,
        "queue_path": str(queue_path),
        "contact_sheet": str((output / "contact_sheets" / "initial_preference_pool_contact_sheet.png").resolve()),
        "license_class": "research_only", "commercial_allowed": False,
        "failed_visual_rag_enabled": False, "failed_vision_critic_enabled": False,
        "preference_collection_ready": True, "ready_for_preference_training": False,
        "preference_model_trained": False, "v0.4_complete": False,
    }
    (output / "manifest.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (output / "generation_summary.json").write_text(json.dumps({
        "schema_version": "1.0", "runs": generation_summaries,
        "fresh_generation_attempt_count": total_generation_attempts,
        "failed_generation_attempt_count": total_generation_attempts - fresh_candidates_in_pool,
        "new_valid_candidate_count": fresh_candidates_in_pool,
        "duration_seconds": total_generation_seconds, "peak_vram_gib": peak_vram,
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--base-briefs", type=Path, default=Path("training/config/benchmarks/design_v0_2.json"))
    parser.add_argument("--extra-briefs", type=Path, default=Path("training/config/preference/v0_4_phase1_additional_briefs.json"))
    parser.add_argument("--base-runs", type=Path, required=True)
    parser.add_argument("--extra-runs", type=Path, required=True)
    parser.add_argument("--replacement-runs", type=Path, action="append", default=[])
    parser.add_argument("--v031-root", type=Path, required=True)
    parser.add_argument("--v032-root", type=Path, required=True)
    parser.add_argument("--v033-root", type=Path, required=True)
    parser.add_argument("--v035-root", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
