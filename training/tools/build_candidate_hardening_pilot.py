"""Build the isolated 5x4 v0.4 Phase 1.1 content-locked review pilot."""

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
from training.preference.v04.diagnostics import (
    audit_candidate_pool,
    write_diagnostic_snapshot,
)
from training.preference.v04.hardening import (
    apply_candidate_style_variant,
    assert_candidate_group_locked,
    evaluate_quality_floor,
    invariant_from_document,
    placeholder_metrics,
    structural_diversity,
    variants_for_category,
)
from training.preference.v04.pairing import (
    candidate_from_directory,
    tournament_pairs,
    write_queue,
)
from training.schemas.design import DesignDocument
from training.typography.fitting import fit_design_typography


CASES = ("spa", "cafe", "sale", "menu", "signage")
DISPLAY_NAMES = {
    "spa": "SPA",
    "cafe": "CAFE",
    "sale": "SALE",
    "menu": "MENU",
    "signage": "SIGNAGE",
}


def _read(path: Path) -> Any:
    return json.loads(path.resolve().read_text(encoding="utf-8"))


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _prompt(case: dict[str, Any]) -> str:
    values = [
        case.get("headline"),
        case.get("subheadline"),
        case.get("body"),
        case.get("cta"),
    ]
    if case.get("items"):
        values.extend(item.get("name") for item in case["items"])
    return " · ".join(str(value) for value in values if value)


def _contact_sheet(rows: list[tuple[str, list[Path]]], output: Path) -> None:
    cell_width, cell_height = 420, 360
    label_height, row_title = 34, 42
    sheet = Image.new(
        "RGB",
        (cell_width * 4, (cell_height + label_height + row_title) * len(rows)),
        "#E8E5DF",
    )
    draw = ImageDraw.Draw(sheet)
    for row_index, (case_id, previews) in enumerate(rows):
        row_y = row_index * (cell_height + label_height + row_title)
        draw.rectangle((0, row_y, sheet.width, row_y + row_title), fill="#171819")
        draw.text((16, row_y + 12), DISPLAY_NAMES[case_id], fill="#FFFFFF")
        for column, path in enumerate(previews):
            x = column * cell_width
            draw.text((x + 12, row_y + row_title + 9), chr(65 + column), fill="#171819")
            with Image.open(path) as source:
                image = ImageOps.contain(
                    source.convert("RGB"),
                    (cell_width - 22, cell_height - 18),
                    method=Image.Resampling.LANCZOS,
                )
            origin_x = x + (cell_width - image.width) // 2
            origin_y = row_y + row_title + label_height + (cell_height - image.height) // 2
            sheet.paste(image, (origin_x, origin_y))
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output, format="PNG", optimize=True)


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
    if case_id == "menu":
        explicit_values = {
            " ".join(str(value).split()).casefold()
            for item in case.get("items", [])
            for value in (item.get("name"), item.get("description"), item.get("price"))
            if value
        }
        for element in document.elements:
            if element.text is None:
                continue
            parts = {
                " ".join(value.split()).casefold()
                for value in element.text.content.splitlines()
                if value.strip()
            }
            if parts and parts.issubset(explicit_values):
                element.metadata = {
                    **element.metadata,
                    "placeholder_only": False,
                    "requires_user_data": False,
                    "benchmark_sample_data": True,
                    "customer_provided": False,
                    "content_provenance": "project_owned_benchmark_sample",
                }
    document.metadata = {
        **document.metadata,
        "brief_id": case["source_prompt_id"],
        "phase1_1_case_id": case_id,
        "candidate_invariant_brief": case,
    }
    return document, case, manifest


def _build_case(
    *,
    source_root: Path,
    output: Path,
    case_id: str,
    max_regeneration_attempts: int,
) -> dict[str, Any]:
    source, case, manifest = _prepare_source(source_root, case_id)
    destination = output / "runs" / case_id
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
    rejection_log = []
    variants = variants_for_category(case_id)
    for index, variant in enumerate(variants, 1):
        candidate_id = f"candidate_{index:02d}"
        candidate_dir = destination / "candidates" / candidate_id
        candidate_dir.mkdir(parents=True)
        regeneration_count = 0
        while True:
            hardened = apply_candidate_style_variant(source, variant)
            fitted, typography = fit_design_typography(hardened, allow_expand=False)
            fitted = DesignDocument.model_validate(fitted.model_dump())
            metrics = evaluate_layout(fitted)
            quality = evaluate_quality_floor(
                fitted,
                metrics,
                regeneration_count=regeneration_count,
            )
            if quality.passed:
                break
            rejection_log.append(
                {
                    "candidate_id": candidate_id,
                    "variant_id": variant.variant_id,
                    "reason": quality.reasons,
                    "metrics": quality.metrics,
                    "regeneration_count": regeneration_count,
                }
            )
            regeneration_count += 1
            if regeneration_count >= max_regeneration_attempts:
                _write(destination / "rejections.json", rejection_log)
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
            "quality_floor_passed": quality.passed,
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
                "generation_version": "candidate_generation_v2_pilot",
                "source_generation": "v0.3.3_asset_aware_successful_path",
                "fresh_qwen_generation": False,
                "deterministic_visual_recomposition": True,
                "failed_visual_rag_enabled": False,
                "failed_vision_critic_enabled": False,
                "variant": variant.model_dump(mode="json"),
                "regeneration_count": regeneration_count,
                "max_regeneration_attempts": max_regeneration_attempts,
            },
        )
        _write(candidate_dir / "typography.json", typography)
        _write(candidate_dir / "invariant.json", invariant.model_dump(mode="json"))
        _write(candidate_dir / "quality_floor.json", quality.model_dump(mode="json"))
        artifact = candidate_from_directory(
            candidate_dir=candidate_dir,
            brief_id=case["source_prompt_id"],
            design_id=f"pilot:{case_id}:{chr(64 + index)}",
            generation_source="v0.4_phase1.1_asset_aware_composition_variant",
            provenance={
                "generation_version": "candidate_generation_v2_pilot",
                "source_milestone": "v0.3.3",
                "layout_family": variant.layout_family,
                "quality_floor_passed": True,
                "content_lock_hash": invariant.content_lock_hash,
                "asset_lock_hash": invariant.asset_lock_hash,
                "business_value_hash": invariant.business_value_hash,
                "canvas_hash": invariant.canvas_hash,
                "visual_rag_enabled": False,
                "vision_critic_enabled": False,
                "human_label": None,
            },
            license_class="research_only",
            commercial_allowed=False,
        )
        candidates.append(artifact)
        invariants.append(invariant)
        documents[artifact.design_id] = fitted
        previews.append(preview)
        rows.append(
            {
                "candidate_id": artifact.design_id,
                "layout_family": variant.layout_family,
                "variant_id": variant.variant_id,
                "content_lock_hash": invariant.content_lock_hash,
                "asset_lock_hash": invariant.asset_lock_hash,
                "business_value_hash": invariant.business_value_hash,
                "canvas_hash": invariant.canvas_hash,
                "quality_floor": quality.model_dump(mode="json"),
                "metrics": full_metrics,
                "preview_path": str(preview),
                "design_path": artifact.design_path,
                "corel_operation_count": len(operations),
            }
        )
    assert_candidate_group_locked(invariants)
    diversity = structural_diversity(documents)
    if not diversity["passes"]:
        _write(
            destination / "diversity_rejections.json",
            {
                "reason": "LOW_DIVERSITY",
                "metrics": diversity,
                "regeneration_count": 0,
                "max_regeneration_attempts": max_regeneration_attempts,
            },
        )
        raise RuntimeError(f"CANDIDATE_POOL_INSUFFICIENT: {case_id}: LOW_DIVERSITY")
    pairs = tournament_pairs(
        brief_id=case["source_prompt_id"],
        prompt=_prompt(case),
        category=case_id,
        candidates=candidates,
        benchmark_sample_data=bool(case.get("benchmark_sample_data", False)),
        customer_provided=bool(case.get("customer_provided", False)),
        provenance={
            "generation_version": "candidate_generation_v2_pilot",
            "quality_floor_passed": True,
            "pairing": "deterministic_tournament_v1",
            "human_label": None,
        },
    )
    _write(destination / "diversity.json", diversity)
    _write(destination / "candidate_rows.json", rows)
    _write(destination / "rejections.json", rejection_log)
    _write(
        destination / "lock_summary.json",
        {
            "content_lock_result": True,
            "asset_lock_result": True,
            "business_value_lock_result": True,
            "canvas_lock_result": True,
            "content_lock_hash": invariants[0].content_lock_hash,
            "asset_lock_hash": invariants[0].asset_lock_hash,
            "business_value_hash": invariants[0].business_value_hash,
            "canvas_hash": invariants[0].canvas_hash,
            "asset_manifest_case_id": manifest["case_id"],
        },
    )
    return {
        "case_id": case_id,
        "brief_id": case["source_prompt_id"],
        "layout_families": [variant.layout_family for variant in variants],
        "candidate_count": 4,
        "content_lock_result": True,
        "asset_lock_result": True,
        "business_value_lock_result": True,
        "canvas_lock_result": True,
        "technical_safety": all(row["quality_floor"]["passed"] for row in rows),
        "quality_floor_passed": True,
        "placeholder_count": sum(int(row["metrics"]["placeholder_count"]) for row in rows),
        "mean_placeholder_area_ratio": mean(
            float(row["metrics"]["placeholder_area_ratio"]) for row in rows
        ),
        "mean_pairwise_candidate_diversity": diversity[
            "mean_pairwise_candidate_diversity"
        ],
        "minimum_pairwise_candidate_diversity": diversity[
            "minimum_pairwise_candidate_diversity"
        ],
        "distinct_layout_family_count": diversity["distinct_layout_family_count"],
        "rejection_count": len(rejection_log),
        "benchmark_sample_data": bool(case.get("benchmark_sample_data", False)),
        "customer_provided": bool(case.get("customer_provided", False)),
        "previews": previews,
        "pairs": pairs,
    }


def build(args: argparse.Namespace) -> dict[str, Any]:
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"pilot output must be new or empty: {output}")
    output.mkdir(parents=True, exist_ok=True)
    old_audit = audit_candidate_pool(args.old_queue)
    _write(args.diagnostic_output / "old_pool_quality_audit.json", old_audit)
    snapshot = write_diagnostic_snapshot(args.reviews_root, args.diagnostic_output)
    rows = [
        _build_case(
            source_root=args.source_root.resolve(),
            output=output,
            case_id=case_id,
            max_regeneration_attempts=args.max_regeneration_attempts,
        )
        for case_id in CASES
    ]
    all_pairs = [pair for row in rows for pair in row.pop("pairs")]
    contact_rows = [(row["case_id"], row.pop("previews")) for row in rows]
    queue_path = write_queue(
        all_pairs,
        output / "review_queue" / "review_queue.jsonl",
    )
    contact_sheet = output / "pilot_contact_sheet_5x4.png"
    _contact_sheet(contact_rows, contact_sheet)
    pilot_diversity = {
        "schema_version": "1.0",
        "case_count": len(rows),
        "mean_pairwise_candidate_diversity": mean(
            float(row["mean_pairwise_candidate_diversity"]) for row in rows
        ),
        "minimum_pairwise_candidate_diversity": min(
            float(row["minimum_pairwise_candidate_diversity"]) for row in rows
        ),
        "distinct_layout_family_count_per_case": {
            row["case_id"]: row["distinct_layout_family_count"] for row in rows
        },
        "all_cases_pass": all(row["distinct_layout_family_count"] >= 3 for row in rows),
        "generic_visual_embedding_used": False,
        "rows": rows,
    }
    pilot_quality = {
        "schema_version": "1.0",
        "quality_floor_version": "v0.4_phase1.1_conservative",
        "candidate_count": 20,
        "technical_pass_count": sum(4 for row in rows if row["technical_safety"]),
        "content_consistency_rate": 1.0,
        "asset_consistency_rate": 1.0,
        "business_value_consistency_rate": 1.0,
        "canvas_consistency_rate": 1.0,
        "placeholder_count": sum(int(row["placeholder_count"]) for row in rows),
        "mean_placeholder_area_ratio": mean(
            float(row["mean_placeholder_area_ratio"]) for row in rows
        ),
        "rejection_count": sum(int(row["rejection_count"]) for row in rows),
        "old_vs_pilot": {
            "old": {
                key: old_audit[key]
                for key in (
                    "content_consistency_rate",
                    "asset_consistency_rate",
                    "business_value_consistency_rate",
                    "canvas_consistency_rate",
                    "mean_pairwise_candidate_diversity",
                    "minimum_pairwise_candidate_diversity",
                    "mean_distinct_layout_family_count",
                    "placeholder_count",
                    "mean_placeholder_area_ratio",
                    "technical_pass_rate",
                )
            },
            "pilot": {
                "content_consistency_rate": 1.0,
                "asset_consistency_rate": 1.0,
                "business_value_consistency_rate": 1.0,
                "canvas_consistency_rate": 1.0,
                "mean_pairwise_candidate_diversity": pilot_diversity[
                    "mean_pairwise_candidate_diversity"
                ],
                "minimum_pairwise_candidate_diversity": pilot_diversity[
                    "minimum_pairwise_candidate_diversity"
                ],
                "mean_distinct_layout_family_count": mean(
                    int(row["distinct_layout_family_count"]) for row in rows
                ),
                "placeholder_count": sum(int(row["placeholder_count"]) for row in rows),
                "mean_placeholder_area_ratio": mean(
                    float(row["mean_placeholder_area_ratio"]) for row in rows
                ),
                "technical_pass_rate": 1.0,
            },
        },
        "human_visual_improvement_claimed": False,
    }
    manifest = {
        "schema_version": "1.0",
        "checkpoint": "Design AI v0.4 Phase 1.1 — Candidate Quality Hardening Pilot",
        "generation_version": "candidate_generation_v2_pilot",
        "source_path": "v0.3.3 asset-aware + v0.3.2 aesthetic hardening lineage",
        "brief_count": 5,
        "candidate_count": 20,
        "categories": list(CASES),
        "review_pair_count": len(all_pairs),
        "queue_path": str(queue_path),
        "contact_sheet": str(contact_sheet),
        "old_human_reviews_preserved": snapshot["human_review_count"],
        "pilot_human_reviews_collected": 0,
        "human_visual_quality_status": "pending",
        "status": "WAITING_FOR_PILOT_HUMAN_REVIEW",
        "full_candidate_pool_regenerated": False,
        "ready_for_preference_training": False,
        "preference_model_trained": False,
        "v0.4_complete": False,
        "production_ready": False,
        "commercial_allowed": False,
        "failed_visual_rag_enabled": False,
        "failed_vision_critic_enabled": False,
        "rows": rows,
    }
    _write(output / "pilot_manifest.json", manifest)
    _write(output / "pilot_quality_report.json", pilot_quality)
    _write(output / "pilot_diversity_report.json", pilot_diversity)
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-root",
        type=Path,
        default=Path("training/artifacts/benchmarks/20260812_design_v0_3_3_real_assets"),
    )
    parser.add_argument(
        "--old-queue",
        type=Path,
        default=Path("training/artifacts/preference/v0_4_initial_pool/review_queue/review_queue.jsonl"),
    )
    parser.add_argument(
        "--reviews-root",
        type=Path,
        default=Path("training/data/human_preferences/v0_4/reviews"),
    )
    parser.add_argument(
        "--diagnostic-output",
        type=Path,
        default=Path("training/artifacts/preference/v0_4_phase1_1_diagnostic"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("training/artifacts/preference/v0_4_phase1_1_candidate_hardening"),
    )
    parser.add_argument("--max-regeneration-attempts", type=int, choices=range(3, 6), default=3)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    print(json.dumps(build(args), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
