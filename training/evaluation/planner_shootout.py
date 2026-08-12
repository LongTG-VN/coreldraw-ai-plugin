"""Shootout benchmark generator comparing Antigravity and Qwen3-1.7B design planners."""

from __future__ import annotations

import hashlib
import json
import os
import random
import time
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from training.evaluation.benchmark_briefs import BENCHMARK_BRIEFS
from training.inference.corel_compiler import compile_corel_operations
from training.inference.planner_base import (
    BaseDesignPlanner,
    ContentLockSpec,
    validate_content_lock,
)
from training.inference.planners import AntigravityDesignPlanner, QwenDesignPlanner
from training.inference.preview import render_preview
from training.preference.v04.models import (
    CandidateArtifactV1,
    ReviewQueueItemV1,
)
from training.schemas.design import DesignDocument


DEFAULT_BENCHMARK_ROOT = Path(
    "training/artifacts/benchmarks/20260812_antigravity_vs_qwen_planner"
)


def run_planner_shootout(
    output_root: Path = DEFAULT_BENCHMARK_ROOT,
    seed: int = 42,
) -> dict[str, Any]:
    """Execute the full controlled shootout benchmark between Antigravity and Qwen."""

    output_root.mkdir(parents=True, exist_ok=True)
    random.seed(seed)

    qwen_planner = QwenDesignPlanner()
    antigravity_planner = AntigravityDesignPlanner()

    planners: list[BaseDesignPlanner] = [qwen_planner, antigravity_planner]

    results_by_planner: dict[str, list[dict[str, Any]]] = {
        "Qwen3-1.7B": [],
        "Antigravity": [],
    }

    all_candidates_flat: list[dict[str, Any]] = []
    anonymous_id_counter = 1

    # Manifest metadata
    manifest = {
        "schema_version": "1.0",
        "benchmark_id": "20260812_antigravity_vs_qwen_planner",
        "briefs_count": len(BENCHMARK_BRIEFS),
        "candidates_per_brief": 4,
        "total_target_candidates": 40,
        "planners": ["Qwen3-1.7B", "Antigravity"],
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    # Save manifest
    with open(output_root / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    # Process all briefs and planners
    for brief in BENCHMARK_BRIEFS:
        for planner in planners:
            planner_slug = "qwen" if planner.name == "Qwen3-1.7B" else "antigravity"
            brief_dir = output_root / planner_slug / brief.brief_id
            brief_dir.mkdir(parents=True, exist_ok=True)

            for c_idx in range(4):
                cand_dir = brief_dir / f"candidate_{c_idx + 1}"
                cand_dir.mkdir(parents=True, exist_ok=True)

                res = planner.plan(brief, candidate_index=c_idx, seed=seed + c_idx)

                # Save design.json
                doc_path = cand_dir / "design.json"
                with open(doc_path, "w", encoding="utf-8") as f:
                    f.write(res.document.model_dump_json(indent=2))

                # Save planner_output.json
                plan_path = cand_dir / "planner_output.json"
                with open(plan_path, "w", encoding="utf-8") as f:
                    f.write(res.plan_v2.model_dump_json(indent=2))

                # Compile Corel operations
                ops = compile_corel_operations(res.document)
                ops_path = cand_dir / "corel_operations.json"
                with open(ops_path, "w", encoding="utf-8") as f:
                    json.dump(ops, f, indent=2)

                # Render preview PNG
                png_path = cand_dir / "preview.png"
                render_preview(res.document, png_path, max_dimension=800)

                # Output CDR artifact (mock / placeholder for headless test environments)
                cdr_path = cand_dir / "output.cdr"
                if not cdr_path.exists():
                    with open(cdr_path, "wb") as f:
                        f.write(b"MOCK_CDR_BINARY_HEADER_" + res.document.sample_id.encode("utf-8"))

                # Metrics for candidate
                content_valid = validate_content_lock(res.document, brief)
                content_sha256 = hashlib.sha256(png_path.read_bytes()).hexdigest()

                anon_id = f"DESIGN_{anonymous_id_counter:03d}"
                anonymous_id_counter += 1

                cand_meta = {
                    "anonymous_id": anon_id,
                    "planner_name": planner.name,
                    "brief_id": brief.brief_id,
                    "category": brief.category,
                    "candidate_index": c_idx + 1,
                    "layout_family": res.layout_family,
                    "latency_seconds": res.latency_seconds,
                    "content_valid": content_valid,
                    "design_path": str(doc_path),
                    "preview_path": str(png_path),
                    "cdr_path": str(cdr_path),
                    "content_sha256": content_sha256,
                }

                # Save metrics.json
                with open(cand_dir / "metrics.json", "w", encoding="utf-8") as f:
                    json.dump(cand_meta, f, indent=2)

                # Save provenance.json
                prov = {
                    "benchmark_sample_data": True,
                    "customer_provided": False,
                    "license_class": "CC0_or_project_owned",
                    "commercial_allowed": True,
                    "planner": planner.name,
                }
                with open(cand_dir / "provenance.json", "w", encoding="utf-8") as f:
                    json.dump(prov, f, indent=2)

                results_by_planner[planner.name].append(cand_meta)
                all_candidates_flat.append(cand_meta)

    # Build Blind Pairwise Review Queue
    blind_dir = output_root / "blind_review"
    blind_dir.mkdir(parents=True, exist_ok=True)

    queue_items: list[dict[str, Any]] = []
    blind_mapping: dict[str, dict[str, str]] = {}
    pair_count = 1

    qwen_cands = results_by_planner["Qwen3-1.7B"]
    ag_cands = results_by_planner["Antigravity"]

    # Match candidates per brief (4 pairings per brief = 20 pairs total)
    for brief in BENCHMARK_BRIEFS:
        q_brief_cands = [c for c in qwen_cands if c["brief_id"] == brief.brief_id]
        a_brief_cands = [c for c in ag_cands if c["brief_id"] == brief.brief_id]

        for q_cand, a_cand in zip(q_brief_cands, a_brief_cands):
            pair_hex = f"{pair_count:024x}"
            pair_id = f"pair:{pair_hex}"
            pair_count += 1

            # Deterministic left/right coin flip
            flip = random.choice([True, False])
            left = a_cand if flip else q_cand
            right = q_cand if flip else a_cand

            cand1_art = CandidateArtifactV1(
                design_id=left["anonymous_id"],
                brief_id=brief.brief_id,
                design_path=left["design_path"],
                preview_path=left["preview_path"],
                content_sha256=left["content_sha256"],
                generation_source=left["planner_name"],
                technically_eligible=True,
                provenance={"planner": left["planner_name"]},
                license_class="CC0_or_project_owned",
                commercial_allowed=True,
            )

            cand2_art = CandidateArtifactV1(
                design_id=right["anonymous_id"],
                brief_id=brief.brief_id,
                design_path=right["design_path"],
                preview_path=right["preview_path"],
                content_sha256=right["content_sha256"],
                generation_source=right["planner_name"],
                technically_eligible=True,
                provenance={"planner": right["planner_name"]},
                license_class="CC0_or_project_owned",
                commercial_allowed=True,
            )

            item = ReviewQueueItemV1(
                pair_id=pair_id,
                brief_id=brief.brief_id,
                prompt=f"Brief: {brief.business_name} - {brief.headline}",
                category=brief.category,
                candidate_1=cand1_art,
                candidate_2=cand2_art,
                pairing_stage="cross",
                benchmark_sample_data=True,
                customer_provided=False,
                provenance={"shootout_benchmark": "20260812_antigravity_vs_qwen_planner"},
                license_class="CC0_or_project_owned",
                commercial_allowed=True,
            )

            queue_items.append(item.model_dump())
            blind_mapping[pair_id] = {
                "design_a_id": left["anonymous_id"],
                "design_a_planner": left["planner_name"],
                "design_b_id": right["anonymous_id"],
                "design_b_planner": right["planner_name"],
            }

    # Write review_queue.jsonl
    queue_file = blind_dir / "review_queue.jsonl"
    with open(queue_file, "w", encoding="utf-8") as f:
        for item in queue_items:
            f.write(json.dumps(item) + "\n")

    # Write blind_mapping.json
    with open(blind_dir / "blind_mapping.json", "w", encoding="utf-8") as f:
        json.dump(blind_mapping, f, indent=2)

    # Generate Contact Sheets
    _create_contact_sheets(all_candidates_flat, blind_dir)

    # Calculate Metrics Summary
    metrics_summary = {
        "total_candidates": len(all_candidates_flat),
        "qwen_candidate_count": len(results_by_planner["Qwen3-1.7B"]),
        "antigravity_candidate_count": len(results_by_planner["Antigravity"]),
        "qwen_technical_pass_rate": sum(1 for c in results_by_planner["Qwen3-1.7B"] if c["content_valid"]) / 20.0,
        "antigravity_technical_pass_rate": sum(1 for c in results_by_planner["Antigravity"] if c["content_valid"]) / 20.0,
        "qwen_distinct_layout_families": len({c["layout_family"] for c in results_by_planner["Qwen3-1.7B"]}),
        "antigravity_distinct_layout_families": len({c["layout_family"] for c in results_by_planner["Antigravity"]}),
        "pairs_generated": len(queue_items),
        "status": "WAITING_FOR_BLIND_HUMAN_REVIEW",
    }

    metrics_dir = output_root / "metrics"
    metrics_dir.mkdir(parents=True, exist_ok=True)
    with open(metrics_dir / "shootout_metrics.json", "w", encoding="utf-8") as f:
        json.dump(metrics_summary, f, indent=2)

    return metrics_summary


def _create_contact_sheets(candidates: list[dict[str, Any]], output_dir: Path) -> None:
    """Create hidden anonymous and unblinded contact sheets for candidate audit."""

    cols = 5
    rows = (len(candidates) + cols - 1) // cols
    tile_w, tile_h = 300, 420
    sheet_w, sheet_h = cols * tile_w, rows * tile_h

    # 1. Hidden Anonymous Contact Sheet
    hidden_sheet = Image.new("RGB", (sheet_w, sheet_h), "#1E293B")
    draw_h = ImageDraw.Draw(hidden_sheet)

    # 2. Unblinded Audit Contact Sheet
    unblinded_sheet = Image.new("RGB", (sheet_w, sheet_h), "#0F172A")
    draw_u = ImageDraw.Draw(unblinded_sheet)

    for idx, c in enumerate(candidates):
        r, col = idx // cols, idx % cols
        x, y = col * tile_w, r * tile_h

        preview_img = Image.open(c["preview_path"]).resize((tile_w - 20, tile_h - 70))

        # Paste preview in hidden sheet
        hidden_sheet.paste(preview_img, (x + 10, y + 10))
        draw_h.rectangle([x + 10, y + tile_h - 55, x + tile_w - 10, y + tile_h - 10], fill="#334155")
        draw_h.text((x + 20, y + tile_h - 45), f"{c['anonymous_id']} ({c['category']})", fill="white")

        # Paste preview in unblinded sheet
        unblinded_sheet.paste(preview_img, (x + 10, y + 10))
        draw_u.rectangle([x + 10, y + tile_h - 55, x + tile_w - 10, y + tile_h - 10], fill="#1E293B")
        draw_u.text(
            (x + 20, y + tile_h - 50),
            f"{c['anonymous_id']} - {c['planner_name']}",
            fill="#38BDF8" if c["planner_name"] == "Antigravity" else "#F43F5E",
        )
        draw_u.text((x + 20, y + tile_h - 30), f"{c['category']} | {c['layout_family']}", fill="#94A3B8")

    hidden_sheet.save(output_dir / "planner_candidates_hidden_contact_sheet.png")
    unblinded_sheet.save(output_dir / "planner_candidates_unblinded_audit.png")
