"""Structured grammar adaptation regression pilot.

Historical Phase 1.3 manually authored grammars are useful as fixtures for layout
adaptation and Corel-operation compilation, but they are not Gold references.
This runner therefore produces regression artifacts only: no fake CDR files, no
human-preference queue, and no claim that FixtureQwenPlanner is a real baseline.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from training.evaluation.benchmark_briefs import BENCHMARK_BRIEFS
from training.gold.adapter import GoldDesignAdapter
from training.gold.library import get_grammars_by_category
from training.inference.corel_compiler import compile_corel_operations
from training.inference.planners import FixtureQwenPlanner
from training.inference.preview import render_preview


GOLD_PILOT_ROOT = Path("training/artifacts/benchmarks/20260812_gold_design_grammar_pilot")


def run_gold_grammar_pilot(
    output_root: Path = GOLD_PILOT_ROOT,
    seed: int = 42,
) -> dict[str, Any]:
    """Generate manual-grammar regression artifacts without aesthetic claims."""
    output_root.mkdir(parents=True, exist_ok=True)

    adapter = GoldDesignAdapter()
    fixture_baseline = FixtureQwenPlanner()
    all_candidates: list[dict[str, Any]] = []
    baseline_candidates: list[dict[str, Any]] = []
    adaptation_reports: list[dict[str, Any]] = []

    manifest = {
        "schema_version": "2.0",
        "benchmark_id": "20260812_gold_design_grammar_pilot",
        "benchmark_validity": "STRUCTURED_GRAMMAR_ADAPTATION_PILOT",
        "manual_grammars": True,
        "real_gold_references": False,
        "baseline_type": "fixture",
        "human_review_ready": False,
        "real_cdr_verified": False,
        "commercial_allowed": False,
        "categories_count": len(BENCHMARK_BRIEFS),
        "candidates_per_brief": 4,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    (output_root / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    candidate_root = output_root / "gold_candidates"
    baseline_root = output_root / "baseline_candidates"
    candidate_root.mkdir(parents=True, exist_ok=True)
    baseline_root.mkdir(parents=True, exist_ok=True)

    counter = 1
    for brief in BENCHMARK_BRIEFS:
        grammars = get_grammars_by_category(brief.category)

        # Fixture baseline is retained only for visual/regression context.
        base_result = fixture_baseline.plan(brief, candidate_index=0, seed=seed)
        base_dir = baseline_root / brief.category.lower()
        base_dir.mkdir(parents=True, exist_ok=True)
        base_design = base_dir / "design.json"
        base_design.write_text(base_result.document.model_dump_json(indent=2), encoding="utf-8")
        base_preview = base_dir / "preview.png"
        render_preview(base_result.document, base_preview, max_dimension=800)
        baseline_candidates.append(
            {
                "category": brief.category,
                "brief_id": brief.brief_id,
                "design_path": str(base_design),
                "preview_path": str(base_preview),
                "planner_name": base_result.planner_name,
                "planner_type": base_result.planner_type,
                "eligible_for_human_baseline_claim": False,
            }
        )

        category_dir = candidate_root / brief.category.lower()
        category_dir.mkdir(parents=True, exist_ok=True)
        for candidate_index in range(4):
            grammar = grammars[candidate_index % len(grammars)]
            candidate_dir = category_dir / f"candidate_{candidate_index + 1}"
            candidate_dir.mkdir(parents=True, exist_ok=True)

            document, adaptation_report = adapter.adapt(
                grammar,
                brief,
                candidate_index=candidate_index,
                seed=seed + candidate_index,
            )
            adaptation_reports.append(adaptation_report)

            design_path = candidate_dir / "design.json"
            design_path.write_text(document.model_dump_json(indent=2), encoding="utf-8")
            (candidate_dir / "gold_grammar.json").write_text(
                grammar.model_dump_json(indent=2), encoding="utf-8"
            )
            (candidate_dir / "adaptation_report.json").write_text(
                json.dumps(adaptation_report, indent=2), encoding="utf-8"
            )

            operations = compile_corel_operations(document)
            operations_path = candidate_dir / "corel_operations.json"
            operations_path.write_text(json.dumps(operations, indent=2), encoding="utf-8")

            preview_path = candidate_dir / "preview.png"
            render_preview(document, preview_path, max_dimension=800)

            # Never manufacture a CDR header. Real CDR generation belongs to the
            # verified Windows/Corel Design API integration path.
            cdr_request = {
                "status": "NOT_GENERATED_REQUIRES_REAL_COREL_API",
                "requested_output_name": "output.cdr",
                "design_path": str(design_path),
                "corel_operations_path": str(operations_path),
                "real_cdr_verified": False,
            }
            (candidate_dir / "cdr_request.json").write_text(
                json.dumps(cdr_request, indent=2), encoding="utf-8"
            )

            anonymous_id = f"MANUAL_GRAMMAR_{counter:03d}"
            counter += 1
            metadata = {
                "anonymous_id": anonymous_id,
                "grammar_id": grammar.grammar_id,
                "grammar_name": grammar.grammar_name,
                "grammar_origin": "MANUALLY_AUTHORED_GRAMMAR",
                "gold_status": grammar.gold_status,
                "category": brief.category,
                "brief_id": brief.brief_id,
                "candidate_index": candidate_index + 1,
                "design_path": str(design_path),
                "preview_path": str(preview_path),
                "cdr_path": None,
                "cdr_status": cdr_request["status"],
                "real_cdr_verified": False,
                "content_sha256": hashlib.sha256(preview_path.read_bytes()).hexdigest(),
                "adaptation": adaptation_report,
            }
            (candidate_dir / "metrics.json").write_text(
                json.dumps(metadata, indent=2), encoding="utf-8"
            )
            (candidate_dir / "provenance.json").write_text(
                json.dumps(
                    {
                        "benchmark_sample_data": True,
                        "customer_provided": False,
                        "grammar_origin": "MANUALLY_AUTHORED_GRAMMAR",
                        "license_class": str(grammar.provenance.get("license_class") or "UNKNOWN"),
                        "commercial_allowed": False,
                        "project_owned": False,
                        "real_gold_reference": False,
                        "real_cdr_verified": False,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            all_candidates.append(metadata)

    _create_contact_sheets(all_candidates, baseline_candidates, output_root)

    slot_rates = [float(report["slot_fill_rate"]) for report in adaptation_reports]
    relationship_rates = [
        float(report["relationship_preservation_rate"]) for report in adaptation_reports
    ]
    deviations = [float(report["grammar_deviation_score"]) for report in adaptation_reports]
    metrics_summary = {
        "status": "STRUCTURED_GRAMMAR_ADAPTATION_PILOT_ONLY",
        "benchmark_validity": "REGRESSION_FIXTURE_ONLY",
        "total_gold_candidates": len(all_candidates),
        "total_baseline_candidates": len(baseline_candidates),
        "categories_processed": len(BENCHMARK_BRIEFS),
        "manual_grammar_count": len({candidate["grammar_id"] for candidate in all_candidates}),
        "real_gold_reference_count": 0,
        "baseline_type": "fixture",
        "human_review_ready": False,
        "human_comparison_queue_created": False,
        "real_cdr_verified": False,
        "commercial_allowed": False,
        "mean_slot_fill_rate": sum(slot_rates) / len(slot_rates) if slot_rates else None,
        "mean_relationship_preservation_rate": (
            sum(relationship_rates) / len(relationship_rates) if relationship_rates else None
        ),
        "mean_grammar_deviation_score": sum(deviations) / len(deviations) if deviations else None,
    }
    metrics_dir = output_root / "metrics"
    metrics_dir.mkdir(parents=True, exist_ok=True)
    (metrics_dir / "gold_pilot_metrics.json").write_text(
        json.dumps(metrics_summary, indent=2), encoding="utf-8"
    )
    return metrics_summary


def _create_contact_sheets(
    candidates: list[dict[str, Any]],
    baselines: list[dict[str, Any]],
    output_dir: Path,
) -> None:
    cols = 4
    rows = len(BENCHMARK_BRIEFS)
    tile_w, tile_h = 280, 390
    sheet = Image.new("RGB", (cols * tile_w, rows * tile_h), "#0F172A")
    draw = ImageDraw.Draw(sheet)

    for idx, candidate in enumerate(candidates):
        row, col = divmod(idx, cols)
        x, y = col * tile_w, row * tile_h
        with Image.open(candidate["preview_path"]) as raw:
            image = raw.convert("RGB")
            image.thumbnail((tile_w - 20, tile_h - 60))
            sheet.paste(image, (x + 10, y + 10))
        draw.rectangle([x + 10, y + tile_h - 45, x + tile_w - 10, y + tile_h - 10], fill="#1E293B")
        draw.text((x + 15, y + tile_h - 40), f"{candidate['anonymous_id']} ({candidate['category']})", fill="#38BDF8")
        draw.text((x + 15, y + tile_h - 24), f"MANUAL: {candidate['grammar_id']}", fill="#94A3B8")
    sheet.save(output_dir / "gold_grammar_pilot_contact_sheet.png")

    if not baselines:
        return
    baseline_sheet = Image.new("RGB", (len(baselines) * tile_w, 2 * tile_h), "#020617")
    baseline_draw = ImageDraw.Draw(baseline_sheet)
    for col, baseline in enumerate(baselines):
        x = col * tile_w
        with Image.open(baseline["preview_path"]) as raw:
            image = raw.convert("RGB")
            image.thumbnail((tile_w - 20, tile_h - 60))
            baseline_sheet.paste(image, (x + 10, 10))
        baseline_draw.text(
            (x + 15, tile_h - 35),
            f"FIXTURE BASELINE - {baseline['category']}",
            fill="#F43F5E",
        )
        candidate = next(c for c in candidates if c["category"] == baseline["category"])
        with Image.open(candidate["preview_path"]) as raw:
            image = raw.convert("RGB")
            image.thumbnail((tile_w - 20, tile_h - 60))
            baseline_sheet.paste(image, (x + 10, tile_h + 10))
        baseline_draw.text(
            (x + 15, 2 * tile_h - 35),
            f"MANUAL GRAMMAR ({candidate['grammar_id']})",
            fill="#10B981",
        )
    baseline_sheet.save(output_dir / "baseline_vs_gold_contact_sheet.png")
