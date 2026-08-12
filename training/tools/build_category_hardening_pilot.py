"""Build the 3x4 human-review mini pilot for v0.4 Phase 1.2."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from statistics import mean
from typing import Any

from PIL import Image, ImageDraw, ImageOps

from training.evaluation.layout_metrics import evaluate_layout
from training.inference.corel_compiler import compile_corel_operations
from training.inference.preview import render_preview
from training.preference.v04.category_hardening import (
    apply_category_hardening_v2,
    category_group_diversity,
    evaluate_category_quality_floor_v2,
    profile_for_category,
    variants_for_category_v2,
)
from training.preference.v04.hardening import (
    assert_candidate_group_locked,
    invariant_from_document,
    placeholder_metrics,
)
from training.preference.v04.pairing import (
    candidate_from_directory,
    tournament_pairs,
    write_queue,
)
from training.schemas.design import DesignDocument
from training.typography.fitting import fit_design_typography


CASES = ("sale", "signage", "spa")
GENERATION_VERSION = "candidate_generation_v3_category_hardened"
QUEUE_ID = "v04_phase1_2_category_pilot"


def _read(path: Path) -> Any:
    return json.loads(path.resolve().read_text(encoding="utf-8"))


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _prompt(case: dict[str, Any]) -> str:
    return " · ".join(
        str(value)
        for value in (
            case.get("headline"),
            case.get("subheadline"),
            case.get("body"),
            case.get("cta"),
        )
        if value
    )


def _prepare_source(
    source_root: Path,
    case_id: str,
) -> tuple[DesignDocument, dict[str, Any], dict[str, Any]]:
    run = source_root / "runs" / case_id
    case = _read(run / "case.json")
    manifest = _read(run / "asset_manifest.json")
    document = DesignDocument.model_validate_json(
        (run / "asset_aware" / "design.json").read_text(encoding="utf-8")
    ).model_copy(deep=True)
    document.metadata = {
        **document.metadata,
        "brief_id": case["source_prompt_id"],
        "phase1_1_case_id": case_id,
        "candidate_invariant_brief": case,
    }
    return document, case, manifest


def _contact_sheet(
    rows: list[tuple[str, list[Path]]],
    output: Path,
    *,
    columns: int,
    group_break: int | None = None,
) -> None:
    cell_width, cell_height = 360, 300
    row_title, label_height = 42, 34
    sheet = Image.new(
        "RGB",
        (cell_width * columns, (cell_height + row_title + label_height) * len(rows)),
        "#E8E5DF",
    )
    draw = ImageDraw.Draw(sheet)
    for row_index, (case_id, previews) in enumerate(rows):
        row_y = row_index * (cell_height + row_title + label_height)
        draw.rectangle((0, row_y, sheet.width, row_y + row_title), fill="#171819")
        draw.text((16, row_y + 12), case_id.upper(), fill="#FFFFFF")
        for column, path in enumerate(previews):
            x = column * cell_width
            if group_break is None:
                label = chr(65 + column)
            else:
                group = "PHASE 1.1" if column < group_break else "PHASE 1.2"
                label = f"{group} · {chr(65 + column % group_break)}"
            draw.text((x + 12, row_y + row_title + 9), label, fill="#171819")
            with Image.open(path) as source:
                image = ImageOps.contain(
                    source.convert("RGB"),
                    (cell_width - 22, cell_height - 18),
                    method=Image.Resampling.LANCZOS,
                )
            origin_x = x + (cell_width - image.width) // 2
            origin_y = row_y + row_title + label_height + (cell_height - image.height) // 2
            sheet.paste(image, (origin_x, origin_y))
        if group_break is not None:
            split_x = cell_width * group_break
            draw.line((split_x, row_y, split_x, row_y + row_title + label_height + cell_height), fill="#A76E2E", width=5)
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output, format="PNG", optimize=True)


def _build_case(
    *,
    source_root: Path,
    output: Path,
    case_id: str,
) -> dict[str, Any]:
    source, case, asset_manifest = _prepare_source(source_root, case_id)
    destination = output / "runs" / case_id
    if destination.exists():
        raise FileExistsError(f"refusing to overwrite pilot run: {destination}")
    destination.mkdir(parents=True)
    shutil.copy2(source_root / "runs" / case_id / "case.json", destination / "case.json")
    shutil.copy2(
        source_root / "runs" / case_id / "asset_manifest.json",
        destination / "asset_manifest.json",
    )
    candidates = []
    documents: dict[str, DesignDocument] = {}
    invariants = []
    previews: list[Path] = []
    rows = []
    all_pairs = []
    for index, variant in enumerate(variants_for_category_v2(case_id), 1):
        candidate_id = f"candidate_{index:02d}"
        candidate_dir = destination / "candidates" / candidate_id
        candidate_dir.mkdir(parents=True)
        hardened = apply_category_hardening_v2(source, variant)
        fitted, typography = fit_design_typography(hardened, allow_expand=False)
        fitted = DesignDocument.model_validate(fitted.model_dump())
        metrics = evaluate_layout(fitted)
        quality = evaluate_category_quality_floor_v2(fitted, metrics)
        if not quality.passed:
            _write(
                candidate_dir / "quality_floor.json",
                quality.model_dump(mode="json"),
            )
            raise RuntimeError(
                f"CANDIDATE_POOL_INSUFFICIENT: {case_id}/{candidate_id}: {quality.reasons}"
            )
        operations = compile_corel_operations(
            fitted,
            width_mm=float(fitted.canvas.width),
            height_mm=float(fitted.canvas.height),
        )
        preview = render_preview(
            fitted,
            candidate_dir / "preview.png",
            max_dimension=1200,
            allow_upscale=True,
        )
        invariant = invariant_from_document(
            fitted,
            brief_id=case["source_prompt_id"],
            brief_payload=case,
        )
        full_metrics = {
            **metrics,
            **placeholder_metrics(fitted),
            "quality_floor_passed": True,
            "quality_floor_version": "category_quality_floor_v2",
            "layout_family": variant.layout_family,
        }
        _write(candidate_dir / "design.json", fitted.model_dump(mode="json"))
        _write(candidate_dir / "corel_operations.json", operations)
        _write(candidate_dir / "metrics.json", full_metrics)
        _write(
            candidate_dir / "validation.json",
            {
                "strict_schema_valid": True,
                "corel_compile_valid": bool(operations),
                "content_lock_valid": True,
                "asset_lock_valid": True,
                "business_value_lock_valid": True,
                "canvas_lock_valid": True,
            },
        )
        _write(
            candidate_dir / "generation.json",
            {
                "generation_version": GENERATION_VERSION,
                "quality_floor_version": "category_quality_floor_v2",
                "source_generation": "v0.3.3_asset_aware_successful_path",
                "fresh_qwen_generation": False,
                "deterministic_category_recomposition": True,
                "failed_visual_rag_enabled": False,
                "failed_vision_critic_enabled": False,
                "variant": variant.model_dump(mode="json"),
            },
        )
        _write(candidate_dir / "typography.json", typography)
        _write(candidate_dir / "invariant.json", invariant.model_dump(mode="json"))
        _write(candidate_dir / "quality_floor.json", quality.model_dump(mode="json"))
        artifact = candidate_from_directory(
            candidate_dir=candidate_dir,
            brief_id=case["source_prompt_id"],
            design_id=f"pilot_v3:{case_id}:{chr(64 + index)}",
            generation_source="v0.4_phase1.2_category_hardening",
            provenance={
                "generation_version": GENERATION_VERSION,
                "source_milestone": "v0.3.3",
                "layout_family": variant.layout_family,
                "category_profile": case_id,
                "quality_floor_version": "category_quality_floor_v2",
                "quality_floor_passed": True,
                "content_lock_hash": invariant.content_lock_hash,
                "asset_lock_hash": invariant.asset_lock_hash,
                "business_value_hash": invariant.business_value_hash,
                "canvas_hash": invariant.canvas_hash,
                "human_label": None,
            },
            license_class="research_only",
            commercial_allowed=False,
        )
        candidates.append(artifact)
        documents[artifact.design_id] = fitted
        invariants.append(invariant)
        previews.append(preview)
        rows.append(
            {
                "candidate_id": artifact.design_id,
                "variant_id": variant.variant_id,
                "layout_family": variant.layout_family,
                "metrics": full_metrics,
                "quality_floor": quality.model_dump(mode="json"),
                "content_lock_hash": invariant.content_lock_hash,
                "asset_lock_hash": invariant.asset_lock_hash,
                "business_value_lock_hash": invariant.business_value_hash,
                "canvas_lock_hash": invariant.canvas_hash,
                "preview_path": str(preview.resolve()),
                "design_path": artifact.design_path,
                "corel_operation_count": len(operations),
            }
        )
    assert_candidate_group_locked(invariants)
    diversity = category_group_diversity(documents)
    if not diversity["passes"]:
        _write(destination / "diversity_rejections.json", diversity)
        raise RuntimeError(f"CANDIDATE_POOL_INSUFFICIENT: {case_id}: NEAR_DUPLICATE")
    pairs = tournament_pairs(
        brief_id=case["source_prompt_id"],
        prompt=_prompt(case),
        category=case_id,
        candidates=candidates,
        benchmark_sample_data=bool(case.get("benchmark_sample_data", False)),
        customer_provided=bool(case.get("customer_provided", False)),
        provenance={
            "queue_id": QUEUE_ID,
            "generation_version": GENERATION_VERSION,
            "quality_floor_version": "category_quality_floor_v2",
            "quality_floor_passed": True,
            "pairing": "deterministic_tournament_v1",
            "human_label": None,
        },
    )
    all_pairs.extend(pairs)
    _write(destination / "candidate_rows.json", rows)
    _write(destination / "diversity.json", diversity)
    _write(
        destination / "lock_summary.json",
        {
            "content_lock_result": True,
            "asset_lock_result": True,
            "business_value_lock_result": True,
            "canvas_lock_result": True,
            "content_lock_hash": invariants[0].content_lock_hash,
            "asset_lock_hash": invariants[0].asset_lock_hash,
            "business_value_lock_hash": invariants[0].business_value_hash,
            "canvas_lock_hash": invariants[0].canvas_hash,
            "asset_manifest_case_id": asset_manifest["case_id"],
        },
    )
    return {
        "case_id": case_id,
        "brief_id": case["source_prompt_id"],
        "profile": profile_for_category(case_id).model_dump(mode="json"),
        "candidate_count": 4,
        "layout_families": [row["layout_family"] for row in rows],
        "content_lock_result": True,
        "asset_lock_result": True,
        "business_value_lock_result": True,
        "canvas_lock_result": True,
        "technical_safety": True,
        "placeholder_count": sum(int(row["metrics"]["placeholder_count"]) for row in rows),
        "mean_placeholder_area_ratio": mean(float(row["metrics"]["placeholder_area_ratio"]) for row in rows),
        "mean_pairwise_candidate_diversity": diversity["mean_pairwise_candidate_diversity"],
        "minimum_pairwise_candidate_diversity": diversity["minimum_pairwise_candidate_diversity"],
        "distinct_layout_family_count": diversity["distinct_layout_family_count"],
        "benchmark_sample_data": bool(case.get("benchmark_sample_data", False)),
        "customer_provided": bool(case.get("customer_provided", False)),
        "previews": previews,
        "pairs": all_pairs,
    }


def build(args: argparse.Namespace) -> dict[str, Any]:
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    for required in (output / "review_analytics.json", output / "selected_categories.json"):
        if not required.is_file():
            raise FileNotFoundError(f"run review analytics first: {required}")
    selected_payload = _read(output / "selected_categories.json")
    selected = tuple(item["category"] for item in selected_payload["categories"])
    if selected != CASES:
        raise RuntimeError(f"analytics selected {selected}; builder is scoped to {CASES}")
    if (output / "mini_pilot_manifest.json").exists() or (output / "review_queue").exists():
        raise FileExistsError(f"refusing to overwrite Phase 1.2 mini pilot: {output}")
    case_rows = [
        _build_case(source_root=args.source_root.resolve(), output=output, case_id=case_id)
        for case_id in CASES
    ]
    all_pairs = [pair for row in case_rows for pair in row.pop("pairs")]
    contact_rows = [(row["case_id"], row.pop("previews")) for row in case_rows]
    queue = write_queue(all_pairs, output / "review_queue" / "review_queue.jsonl")
    mini_contact = output / "mini_pilot_contact_sheet.png"
    _contact_sheet(contact_rows, mini_contact, columns=4)
    comparison_rows = []
    for case_id, new_previews in contact_rows:
        old_previews = [
            args.phase1_1_root.resolve()
            / "runs"
            / case_id
            / "candidates"
            / f"candidate_{index:02d}"
            / "preview.png"
            for index in range(1, 5)
        ]
        if not all(path.is_file() for path in old_previews):
            raise FileNotFoundError(f"Phase 1.1 representative group missing for {case_id}")
        comparison_rows.append((case_id, old_previews + new_previews))
    old_vs_new = output / "old_vs_new_contact_sheet.png"
    _contact_sheet(comparison_rows, old_vs_new, columns=8, group_break=4)
    diversity_report = {
        "schema_version": "1.0",
        "generation_version": GENERATION_VERSION,
        "category_count": 3,
        "mean_pairwise_candidate_diversity": mean(float(row["mean_pairwise_candidate_diversity"]) for row in case_rows),
        "minimum_pairwise_candidate_diversity": min(float(row["minimum_pairwise_candidate_diversity"]) for row in case_rows),
        "distinct_layout_family_count_per_category": {row["case_id"]: row["distinct_layout_family_count"] for row in case_rows},
        "all_categories_pass": all(row["distinct_layout_family_count"] >= 3 for row in case_rows),
        "rows": case_rows,
    }
    quality_report = {
        "schema_version": "1.0",
        "quality_floor_version": "category_quality_floor_v2",
        "generation_version": GENERATION_VERSION,
        "candidate_count": 12,
        "technical_pass_count": 12,
        "strict_schema_validity": 1.0,
        "corel_compile_rate": 1.0,
        "content_lock_rate": 1.0,
        "asset_lock_rate": 1.0,
        "business_value_lock_rate": 1.0,
        "canvas_lock_rate": 1.0,
        "placeholder_count": sum(int(row["placeholder_count"]) for row in case_rows),
        "human_visual_improvement_claimed": False,
        "human_gate_status": "WAITING_FOR_CATEGORY_PILOT_HUMAN_REVIEW",
    }
    manifest = {
        "schema_version": "1.0",
        "checkpoint": "Design AI v0.4 Phase 1.2 — Category-Focused Hardening Mini Pilot",
        "queue_id": QUEUE_ID,
        "generation_version": GENERATION_VERSION,
        "quality_floor_version": "category_quality_floor_v2",
        "source_path": "v0.3.3 asset-aware successful path",
        "category_count": 3,
        "brief_count": 3,
        "candidate_count": 12,
        "categories": list(CASES),
        "review_pair_count": len(all_pairs),
        "queue_path": str(queue.resolve()),
        "mini_pilot_contact_sheet": str(mini_contact.resolve()),
        "old_vs_new_contact_sheet": str(old_vs_new.resolve()),
        "human_visual_quality_status": "pending",
        "status": "WAITING_FOR_CATEGORY_PILOT_HUMAN_REVIEW",
        "full_candidate_pool_regenerated": False,
        "ready_for_preference_training": False,
        "preference_model_trained": False,
        "v0.4_complete": False,
        "production_ready": False,
        "commercial_allowed": False,
        "failed_visual_rag_enabled": False,
        "failed_vision_critic_enabled": False,
        "rows": case_rows,
    }
    _write(output / "mini_pilot_manifest.json", manifest)
    _write(output / "mini_pilot_quality_report.json", quality_report)
    _write(output / "mini_pilot_diversity_report.json", diversity_report)
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-root",
        type=Path,
        default=Path("training/artifacts/benchmarks/20260812_design_v0_3_3_real_assets"),
    )
    parser.add_argument(
        "--phase1-1-root",
        type=Path,
        default=Path("training/artifacts/preference/v0_4_phase1_1_candidate_hardening"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("training/artifacts/preference/v0_4_phase1_2_category_hardening"),
    )
    return parser


def main() -> int:
    print(json.dumps(build(build_parser().parse_args()), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
