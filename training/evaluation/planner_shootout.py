"""Deterministic planner-adapter framework smoke.

The historical file name is preserved for compatibility, but this module does not
represent an Antigravity-vs-Qwen AI benchmark. Both planners are deterministic
fixtures. The runner validates shared contracts/artifact plumbing only and never
creates human-review labels or fake CorelDRAW files.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from training.evaluation.benchmark_briefs import BENCHMARK_BRIEFS
from training.inference.corel_compiler import compile_corel_operations
from training.inference.planner_base import BaseDesignPlanner, validate_content_lock
from training.inference.planners import FixtureAntigravityPlanner, FixtureQwenPlanner
from training.inference.preview import render_preview


DEFAULT_BENCHMARK_ROOT = Path(
    "training/artifacts/benchmarks/20260812_antigravity_vs_qwen_planner"
)


def run_planner_shootout(
    output_root: Path = DEFAULT_BENCHMARK_ROOT,
    seed: int = 42,
) -> dict[str, Any]:
    """Run the deterministic adapter framework smoke; never produce preference data."""
    output_root.mkdir(parents=True, exist_ok=True)

    planners: list[BaseDesignPlanner] = [FixtureQwenPlanner(), FixtureAntigravityPlanner()]
    results_by_planner: dict[str, list[dict[str, Any]]] = {
        "Qwen3-1.7B": [],
        "Antigravity": [],
    }
    all_candidates: list[dict[str, Any]] = []
    anonymous_counter = 1

    manifest = {
        "schema_version": "2.0",
        "benchmark_id": "20260812_antigravity_vs_qwen_planner",
        "benchmark_validity": "DETERMINISTIC_ADAPTER_FRAMEWORK_SMOKE",
        "valid_for_ai_planner_comparison": False,
        "planners_are_fixtures": True,
        "human_review_ready": False,
        "review_queue_created": False,
        "real_cdr_verified": False,
        "commercial_allowed": False,
        "briefs_count": len(BENCHMARK_BRIEFS),
        "candidates_per_brief": 4,
        "total_target_candidates": 40,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    (output_root / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    for brief in BENCHMARK_BRIEFS:
        for planner in planners:
            planner_slug = "qwen_fixture" if planner.name == "Qwen3-1.7B" else "antigravity_fixture"
            brief_dir = output_root / planner_slug / brief.brief_id
            brief_dir.mkdir(parents=True, exist_ok=True)

            for candidate_index in range(4):
                candidate_dir = brief_dir / f"candidate_{candidate_index + 1}"
                candidate_dir.mkdir(parents=True, exist_ok=True)
                result = planner.plan(brief, candidate_index=candidate_index, seed=seed + candidate_index)

                design_path = candidate_dir / "design.json"
                design_path.write_text(result.document.model_dump_json(indent=2), encoding="utf-8")
                (candidate_dir / "planner_output.json").write_text(
                    result.plan_v2.model_dump_json(indent=2), encoding="utf-8"
                )

                operations = compile_corel_operations(result.document)
                operations_path = candidate_dir / "corel_operations.json"
                operations_path.write_text(json.dumps(operations, indent=2), encoding="utf-8")

                preview_path = candidate_dir / "preview.png"
                render_preview(result.document, preview_path, max_dimension=800)

                (candidate_dir / "cdr_request.json").write_text(
                    json.dumps(
                        {
                            "status": "NOT_GENERATED_REQUIRES_REAL_COREL_API",
                            "requested_output_name": "output.cdr",
                            "real_cdr_verified": False,
                            "design_path": str(design_path),
                            "corel_operations_path": str(operations_path),
                        },
                        indent=2,
                    ),
                    encoding="utf-8",
                )

                anonymous_id = f"FIXTURE_DESIGN_{anonymous_counter:03d}"
                anonymous_counter += 1
                metadata = {
                    "anonymous_id": anonymous_id,
                    "planner_name": planner.name,
                    "planner_type": result.planner_type,
                    "brief_id": brief.brief_id,
                    "category": brief.category,
                    "candidate_index": candidate_index + 1,
                    "layout_family": result.layout_family,
                    "latency_seconds": result.latency_seconds,
                    "content_valid": validate_content_lock(result.document, brief),
                    "design_path": str(design_path),
                    "preview_path": str(preview_path),
                    "cdr_path": None,
                    "real_cdr_verified": False,
                    "content_sha256": hashlib.sha256(preview_path.read_bytes()).hexdigest(),
                }
                (candidate_dir / "metrics.json").write_text(
                    json.dumps(metadata, indent=2), encoding="utf-8"
                )
                (candidate_dir / "provenance.json").write_text(
                    json.dumps(
                        {
                            "benchmark_sample_data": True,
                            "planner": planner.name,
                            "planner_type": "fixture",
                            "ai_planner_invoked": False,
                            "license_class": "SYNTHETIC_FIXTURE",
                            "commercial_allowed": False,
                            "real_cdr_verified": False,
                        },
                        indent=2,
                    ),
                    encoding="utf-8",
                )

                results_by_planner[planner.name].append(metadata)
                all_candidates.append(metadata)

    audit_dir = output_root / "framework_audit"
    audit_dir.mkdir(parents=True, exist_ok=True)
    _create_contact_sheets(all_candidates, audit_dir)

    qwen_results = results_by_planner["Qwen3-1.7B"]
    antigravity_results = results_by_planner["Antigravity"]
    metrics = {
        "status": "DETERMINISTIC_ADAPTER_FRAMEWORK_SMOKE",
        "benchmark_validity": "NOT_VALID_FOR_AI_PLANNER_COMPARISON",
        "total_candidates": len(all_candidates),
        "qwen_candidate_count": len(qwen_results),
        "antigravity_candidate_count": len(antigravity_results),
        "qwen_technical_pass_rate": sum(1 for row in qwen_results if row["content_valid"]) / max(1, len(qwen_results)),
        "antigravity_technical_pass_rate": sum(1 for row in antigravity_results if row["content_valid"]) / max(1, len(antigravity_results)),
        "qwen_distinct_layout_families": len({row["layout_family"] for row in qwen_results}),
        "antigravity_distinct_layout_families": len({row["layout_family"] for row in antigravity_results}),
        "pairs_generated": 0,
        "human_review_ready": False,
        "review_queue_created": False,
        "real_cdr_verified": False,
        "commercial_allowed": False,
    }
    metrics_dir = output_root / "metrics"
    metrics_dir.mkdir(parents=True, exist_ok=True)
    (metrics_dir / "shootout_metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    return metrics


def _create_contact_sheets(candidates: list[dict[str, Any]], output_dir: Path) -> None:
    """Create clearly labeled fixture-only contact sheets for pipeline audit."""
    cols = 5
    rows = (len(candidates) + cols - 1) // cols
    tile_w, tile_h = 300, 420
    sheet = Image.new("RGB", (cols * tile_w, rows * tile_h), "#0F172A")
    draw = ImageDraw.Draw(sheet)

    for index, candidate in enumerate(candidates):
        row, col = divmod(index, cols)
        x, y = col * tile_w, row * tile_h
        with Image.open(candidate["preview_path"]) as raw:
            image = raw.convert("RGB")
            image.thumbnail((tile_w - 20, tile_h - 70))
            sheet.paste(image, (x + 10, y + 10))
        draw.rectangle([x + 10, y + tile_h - 55, x + tile_w - 10, y + tile_h - 10], fill="#1E293B")
        draw.text(
            (x + 20, y + tile_h - 48),
            f"{candidate['anonymous_id']} - FIXTURE",
            fill="#F59E0B",
        )
        draw.text(
            (x + 20, y + tile_h - 28),
            f"{candidate['planner_name']} | {candidate['category']} | {candidate['layout_family']}",
            fill="#94A3B8",
        )

    sheet.save(output_dir / "deterministic_adapter_contact_sheet.png")
