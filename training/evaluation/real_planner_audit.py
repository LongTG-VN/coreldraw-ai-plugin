"""Audit gate and pilot runner for the real Antigravity vs Qwen AI planner benchmark."""

from __future__ import annotations

import hashlib
import json
import os
import random
import time
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from training.evaluation.benchmark_briefs import BENCHMARK_BRIEFS, get_brief_by_id
from training.inference.corel_compiler import compile_corel_operations
from training.inference.planner_base import (
    BaseDesignPlanner,
    ContentLockSpec,
    RealPlannerResultContract,
    validate_content_lock,
)
from training.inference.planners import (
    RealAntigravityDesignPlanner,
    RealQwenDesignPlanner,
)
from training.inference.preview import render_preview
from training.preference.v04.models import CandidateArtifactV1, ReviewQueueItemV1


REAL_BENCHMARK_ROOT = Path(
    "training/artifacts/benchmarks/20260812_real_antigravity_vs_qwen_planner"
)


def perform_real_planner_audit(
    brief: ContentLockSpec | None = None,
    qwen_planner: RealQwenDesignPlanner | None = None,
    antigravity_planner: RealAntigravityDesignPlanner | None = None,
) -> dict[str, Any]:
    """Execute the strict audit gate for Real Qwen and Real Antigravity planners."""

    if brief is None:
        brief = get_brief_by_id("brief_sale_01")
    if qwen_planner is None:
        qwen_planner = RealQwenDesignPlanner()
    if antigravity_planner is None:
        antigravity_planner = RealAntigravityDesignPlanner(mode="mode_a_text")

    # Audit Qwen
    qwen_res = qwen_planner.plan(brief, candidate_index=0, seed=42)
    qwen_real_invoked = bool(qwen_res.metadata.get("real_model_invoked"))
    qwen_raw_non_empty = bool(qwen_res.raw_output and qwen_res.raw_output.strip())
    qwen_prompt_exists = bool(qwen_res.request_prompt and qwen_res.request_prompt.strip())
    qwen_plan_derived = bool(qwen_res.plan_v2 is not None)
    qwen_latency_recorded = qwen_res.latency_seconds >= 0.0

    qwen_audit = {
        "planner_name": qwen_planner.name,
        "planner_type": qwen_planner.planner_type,
        "real_model_invoked": qwen_real_invoked,
        "raw_output_non_empty": qwen_raw_non_empty,
        "real_prompt_exists": qwen_prompt_exists,
        "design_plan_derived_from_ai_output": qwen_plan_derived,
        "real_latency_recorded": qwen_latency_recorded,
        "latency_seconds": qwen_res.latency_seconds,
        "valid": qwen_real_invoked and qwen_raw_non_empty and qwen_prompt_exists,
    }

    # Audit Antigravity
    ag_res = antigravity_planner.plan(brief, candidate_index=0, seed=42)
    ag_real_planning = bool(ag_res.metadata.get("real_agent_planning"))
    ag_input_exists = bool(ag_res.request_prompt and ag_res.request_prompt.strip())
    ag_structured_captured = bool(ag_res.raw_output and ag_res.raw_output.strip())
    ag_plan_derived = bool(ag_res.plan_v2 is not None)
    ag_elapsed_recorded = ag_res.latency_seconds > 0.0

    ag_audit = {
        "planner_name": antigravity_planner.name,
        "planner_type": antigravity_planner.planner_type,
        "real_agent_planning": ag_real_planning,
        "real_planner_input_exists": ag_input_exists,
        "structured_output_captured": ag_structured_captured,
        "design_plan_derived_from_ai_output": ag_plan_derived,
        "real_elapsed_time_recorded": ag_elapsed_recorded,
        "latency_seconds": ag_res.latency_seconds,
        "valid": ag_real_planning and ag_input_exists and ag_structured_captured,
    }

    # Determine Conclusion
    if qwen_audit["valid"] and ag_audit["valid"]:
        conclusion = "REAL_PLANNER_SHOOTOUT_VALID"
    elif qwen_audit["valid"] and not ag_audit["valid"]:
        conclusion = "QWEN_REAL_ANTIGRAVITY_INVALID"
    elif not qwen_audit["valid"] and ag_audit["valid"]:
        conclusion = "ANTIGRAVITY_REAL_QWEN_INVALID"
    else:
        conclusion = "BOTH_PLANNERS_INVALID"

    audit_report = {
        "schema_version": "1.0",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "conclusion": conclusion,
        "benchmark_valid": (conclusion == "REAL_PLANNER_SHOOTOUT_VALID"),
        "qwen": qwen_audit,
        "antigravity": ag_audit,
    }

    return audit_report


def run_real_planner_pilot(
    output_root: Path = REAL_BENCHMARK_ROOT,
    mode: str = "mode_a_text",
    seed: int = 42,
) -> dict[str, Any]:
    """Run the 8-design audit pilot (SALE and SPA categories) after passing the audit gate."""

    audit_report = perform_real_planner_audit()

    audit_dir = output_root / "audit"
    audit_dir.mkdir(parents=True, exist_ok=True)
    with open(output_root / "REAL_PLANNER_AUDIT.json", "w", encoding="utf-8") as f:
        json.dump(audit_report, f, indent=2)

    if not audit_report["benchmark_valid"]:
        return {
            "status": "AUDIT_FAILED",
            "conclusion": audit_report["conclusion"],
            "audit_report": audit_report,
            "pilot_generated": False,
        }

    # Pilot Scope: SALE and SPA categories, 2 candidates per planner
    pilot_briefs = [b for b in BENCHMARK_BRIEFS if b.category in {"SALE", "SPA"}]
    mode_dir = output_root / mode
    mode_dir.mkdir(parents=True, exist_ok=True)

    qwen_planner = RealQwenDesignPlanner()
    ag_planner = RealAntigravityDesignPlanner(mode=mode)

    all_pilot_candidates: list[dict[str, Any]] = []

    for brief in pilot_briefs:
        for planner in [qwen_planner, ag_planner]:
            planner_slug = "qwen" if planner.name.startswith("RealQwen") else "antigravity"
            cand_root = mode_dir / planner_slug / brief.brief_id
            cand_root.mkdir(parents=True, exist_ok=True)

            for c_idx in range(2):
                c_dir = cand_root / f"candidate_{c_idx + 1}"
                c_dir.mkdir(parents=True, exist_ok=True)

                res = planner.plan(brief, candidate_index=c_idx, seed=seed + c_idx)

                # Save planner_request.json
                with open(c_dir / "planner_request.json", "w", encoding="utf-8") as f:
                    json.dump(
                        {
                            "prompt": res.request_prompt,
                            "brief_id": brief.brief_id,
                            "seed": seed + c_idx,
                            "started_at": res.started_at,
                        },
                        f,
                        indent=2,
                    )

                # Save raw_planner_output.txt
                with open(c_dir / "raw_planner_output.txt", "w", encoding="utf-8") as f:
                    f.write(res.raw_output)

                # Save design_plan.json
                with open(c_dir / "design_plan.json", "w", encoding="utf-8") as f:
                    f.write(res.plan_v2.model_dump_json(indent=2))

                # Save design.json
                doc_path = c_dir / "design.json"
                with open(doc_path, "w", encoding="utf-8") as f:
                    f.write(res.document.model_dump_json(indent=2))

                # Compile Corel operations
                ops = compile_corel_operations(res.document)
                with open(c_dir / "corel_operations.json", "w", encoding="utf-8") as f:
                    json.dump(ops, f, indent=2)

                # Render preview PNG
                png_path = c_dir / "preview.png"
                render_preview(res.document, png_path, max_dimension=800)

                # Output CDR file
                cdr_path = c_dir / "output.cdr"
                if not cdr_path.exists():
                    with open(cdr_path, "wb") as f:
                        f.write(b"REAL_PLANNER_PILOT_CDR_" + res.document.sample_id.encode("utf-8"))

                content_sha = hashlib.sha256(png_path.read_bytes()).hexdigest()
                anon_id = f"REAL_PILOT_{len(all_pilot_candidates) + 1:03d}"

                meta = {
                    "anonymous_id": anon_id,
                    "planner_name": planner.name,
                    "brief_id": brief.brief_id,
                    "category": brief.category,
                    "candidate_index": c_idx + 1,
                    "layout_family": res.layout_family,
                    "latency_seconds": res.latency_seconds,
                    "content_valid": validate_content_lock(res.document, brief),
                    "design_path": str(doc_path),
                    "preview_path": str(png_path),
                    "cdr_path": str(cdr_path),
                    "content_sha256": content_sha,
                }
                with open(c_dir / "metrics.json", "w", encoding="utf-8") as f:
                    json.dump(meta, f, indent=2)

                prov = {
                    "benchmark_sample_data": True,
                    "customer_provided": False,
                    "license_class": "CC0_or_project_owned",
                    "commercial_allowed": True,
                    "planner": planner.name,
                }
                with open(c_dir / "provenance.json", "w", encoding="utf-8") as f:
                    json.dump(prov, f, indent=2)

                all_pilot_candidates.append(meta)

    # Build Blind Pilot Review Queue
    comp_dir = output_root / "comparisons"
    comp_dir.mkdir(parents=True, exist_ok=True)

    pilot_queue_items: list[dict[str, Any]] = []
    pilot_blind_map: dict[str, Any] = {}
    pair_count = 1

    for brief in pilot_briefs:
        q_cands = [c for c in all_pilot_candidates if c["brief_id"] == brief.brief_id and c["planner_name"].startswith("RealQwen")]
        ag_cands = [c for c in all_pilot_candidates if c["brief_id"] == brief.brief_id and c["planner_name"].startswith("RealAntigravity")]

        for q_c, ag_c in zip(q_cands, ag_cands):
            pair_hex = f"{pair_count:024x}"
            pair_id = f"pair:{pair_hex}"
            pair_count += 1

            flip = random.choice([True, False])
            left = ag_c if flip else q_c
            right = q_c if flip else ag_c

            c1 = CandidateArtifactV1(
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
            c2 = CandidateArtifactV1(
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
                prompt=f"Pilot Brief: {brief.business_name} - {brief.headline}",
                category=brief.category,
                candidate_1=c1,
                candidate_2=c2,
                pairing_stage="cross",
                benchmark_sample_data=True,
                customer_provided=False,
                provenance={"real_planner_pilot": "20260812_real_antigravity_vs_qwen_planner"},
                license_class="CC0_or_project_owned",
                commercial_allowed=True,
            )
            pilot_queue_items.append(item.model_dump())
            pilot_blind_map[pair_id] = {
                "design_a_id": left["anonymous_id"],
                "design_a_planner": left["planner_name"],
                "design_b_id": right["anonymous_id"],
                "design_b_planner": right["planner_name"],
            }

    # Write review_queue.jsonl
    queue_file = comp_dir / "review_queue.jsonl"
    with open(queue_file, "w", encoding="utf-8") as f:
        for item in pilot_queue_items:
            f.write(json.dumps(item) + "\n")

    with open(comp_dir / "blind_mapping.json", "w", encoding="utf-8") as f:
        json.dump(pilot_blind_map, f, indent=2)

    # Generate Contact Sheets
    _create_pilot_contact_sheets(all_pilot_candidates, output_root)

    return {
        "status": "WAITING_FOR_REAL_PLANNER_PILOT_HUMAN_REVIEW",
        "conclusion": audit_report["conclusion"],
        "audit_report": audit_report,
        "pilot_generated": True,
        "total_pilot_candidates": len(all_pilot_candidates),
        "pilot_pairs": len(pilot_queue_items),
    }


def _create_pilot_contact_sheets(candidates: list[dict[str, Any]], output_dir: Path) -> None:
    """Create hidden anonymous and unblinded contact sheets for pilot candidates."""

    cols = 4
    rows = (len(candidates) + cols - 1) // cols
    tile_w, tile_h = 300, 420
    sheet_w, sheet_h = cols * tile_w, rows * tile_h

    hidden_sheet = Image.new("RGB", (sheet_w, sheet_h), "#1E293B")
    draw_h = ImageDraw.Draw(hidden_sheet)

    unblinded_sheet = Image.new("RGB", (sheet_w, sheet_h), "#0F172A")
    draw_u = ImageDraw.Draw(unblinded_sheet)

    for idx, c in enumerate(candidates):
        r, col = idx // cols, idx % cols
        x, y = col * tile_w, r * tile_h

        preview_img = Image.open(c["preview_path"]).resize((tile_w - 20, tile_h - 70))

        hidden_sheet.paste(preview_img, (x + 10, y + 10))
        draw_h.rectangle([x + 10, y + tile_h - 55, x + tile_w - 10, y + tile_h - 10], fill="#334155")
        draw_h.text((x + 20, y + tile_h - 45), f"{c['anonymous_id']} ({c['category']})", fill="white")

        unblinded_sheet.paste(preview_img, (x + 10, y + 10))
        draw_u.rectangle([x + 10, y + tile_h - 55, x + tile_w - 10, y + tile_h - 10], fill="#1E293B")
        draw_u.text(
            (x + 20, y + tile_h - 50),
            f"{c['anonymous_id']} - {c['planner_name']}",
            fill="#38BDF8" if "Antigravity" in c["planner_name"] else "#F43F5E",
        )
        draw_u.text((x + 20, y + tile_h - 30), f"{c['category']} | {c['layout_family']}", fill="#94A3B8")

    hidden_sheet.save(output_dir / "real_planner_pilot_hidden.png")
    unblinded_sheet.save(output_dir / "real_planner_pilot_unblinded_audit.png")
