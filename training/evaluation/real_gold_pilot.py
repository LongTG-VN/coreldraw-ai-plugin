"""Stabilized real-reference Gold Grammar research pilot.

The runner is intentionally conservative:
- source IDs must be explicitly human-approved;
- research-dataset rights remain non-commercial;
- no fake ``.cdr`` file is ever written;
- a fixture planner is never silently presented as a real baseline;
- provenance checks do not claim more than they verify.
"""

from __future__ import annotations

import hashlib
import json
import random
import time
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from training.evaluation.benchmark_briefs import get_brief_by_id
from training.gold.adapter import GoldDesignAdapter
from training.gold.real_pipeline import (
    DEFAULT_APPROVED_MANIFEST_PATH,
    DEFAULT_DATASET_PATH,
    GENPOSTER_COMMERCIAL_ALLOWED,
    GENPOSTER_LICENSE_CLASS,
    GoldSourceApprovalRequired,
    GoldSourceManifestError,
    build_real_gold_library,
)
from training.inference.corel_compiler import compile_corel_operations
from training.inference.planner_base import BaseDesignPlanner
from training.inference.preview import render_preview


REAL_PILOT_ROOT = Path("training/artifacts/benchmarks/20260812_real_gold_grammar_pilot")


def run_real_gold_grammar_pilot(
    output_root: Path = REAL_PILOT_ROOT,
    seed: int = 42,
    *,
    dataset_path: Path = DEFAULT_DATASET_PATH,
    approved_manifest_path: Path = DEFAULT_APPROVED_MANIFEST_PATH,
    baseline_planner: BaseDesignPlanner | None = None,
) -> dict[str, Any]:
    """Run a research-only SALE/SPA adaptation pilot from approved source IDs.

    The function never produces a CorelDRAW file by itself. It prepares validated
    operations for the existing real Corel Design API and records that export as a
    pending external step.
    """
    output_root.mkdir(parents=True, exist_ok=True)
    random.seed(seed)

    try:
        real_grammars, inventory = build_real_gold_library(
            dataset_path=dataset_path,
            approved_manifest_path=approved_manifest_path,
        )
    except GoldSourceApprovalRequired as exc:
        return {
            "status": "WAITING_FOR_SOURCE_HUMAN_APPROVAL",
            "conclusion": "SOURCE_APPROVAL_REQUIRED",
            "pilot_generated": False,
            "reason": str(exc),
            "commercial_allowed": False,
        }
    except GoldSourceManifestError as exc:
        return {
            "status": "REAL_GOLD_SOURCE_MANIFEST_INVALID",
            "conclusion": "SOURCE_MANIFEST_INVALID",
            "pilot_generated": False,
            "reason": str(exc),
            "commercial_allowed": False,
        }

    target_briefs = [get_brief_by_id("brief_sale_01"), get_brief_by_id("brief_spa_01")]
    adapter = GoldDesignAdapter()

    all_candidates: list[dict[str, Any]] = []
    baseline_candidates: list[dict[str, Any]] = []
    gold_dir = output_root / "real_gold_candidates"
    gold_dir.mkdir(parents=True, exist_ok=True)
    baseline_dir = output_root / "baseline_candidates"
    baseline_dir.mkdir(parents=True, exist_ok=True)

    candidate_counter = 1
    for brief in target_briefs:
        category_grammars = [g for g in real_grammars if g.category.upper() == brief.category.upper()]
        if len(category_grammars) < 3:
            return {
                "status": "REAL_GOLD_SOURCE_DATA_REQUIRED",
                "conclusion": "INSUFFICIENT_APPROVED_SOURCES",
                "pilot_generated": False,
                "category": brief.category,
                "approved_source_count": len(category_grammars),
                "commercial_allowed": False,
            }

        if baseline_planner is not None:
            baseline_result = baseline_planner.plan(brief, candidate_index=0, seed=seed)
            base_category_dir = baseline_dir / brief.category.lower()
            base_category_dir.mkdir(parents=True, exist_ok=True)
            base_design_path = base_category_dir / "design.json"
            base_design_path.write_text(
                baseline_result.document.model_dump_json(indent=2), encoding="utf-8"
            )
            base_preview_path = base_category_dir / "preview.png"
            render_preview(baseline_result.document, base_preview_path, max_dimension=800)
            baseline_candidates.append(
                {
                    "category": brief.category,
                    "brief_id": brief.brief_id,
                    "design_path": str(base_design_path),
                    "preview_path": str(base_preview_path),
                    "planner_name": baseline_result.planner_name,
                    "planner_type": baseline_result.planner_type,
                    "eligible_for_human_baseline_claim": baseline_result.planner_type != "fixture",
                }
            )

        category_dir = gold_dir / brief.category.lower()
        category_dir.mkdir(parents=True, exist_ok=True)
        for candidate_index in range(4):
            grammar = category_grammars[candidate_index % len(category_grammars)]
            candidate_dir = category_dir / f"candidate_{candidate_index + 1}"
            candidate_dir.mkdir(parents=True, exist_ok=True)

            document, adaptation_report = adapter.adapt(
                grammar,
                brief,
                candidate_index=candidate_index,
                seed=seed + candidate_index,
            )
            design_path = candidate_dir / "design.json"
            design_path.write_text(document.model_dump_json(indent=2), encoding="utf-8")
            (candidate_dir / "grammar.json").write_text(
                grammar.model_dump_json(indent=2), encoding="utf-8"
            )

            source_reference = {
                "source_design_id": grammar.provenance.get("source_design_id"),
                "source_sha256": grammar.provenance.get("source_sha256"),
                "extracted_from_real_design": grammar.provenance.get("extracted_from_real_design") is True,
                "gold_status": grammar.gold_status,
                "human_quality_status": grammar.provenance.get("human_quality_status"),
                "human_approved": grammar.provenance.get("human_approved") is True,
                "license_class": grammar.provenance.get("license_class"),
                "commercial_allowed": bool(grammar.provenance.get("commercial_allowed", False)),
            }
            (candidate_dir / "source_reference.json").write_text(
                json.dumps(source_reference, indent=2), encoding="utf-8"
            )
            (candidate_dir / "adaptation_report.json").write_text(
                json.dumps(adaptation_report, indent=2), encoding="utf-8"
            )

            operations = compile_corel_operations(document)
            operations_path = candidate_dir / "corel_operations.json"
            operations_path.write_text(json.dumps(operations, indent=2), encoding="utf-8")

            preview_path = candidate_dir / "preview.png"
            render_preview(document, preview_path, max_dimension=800)

            # IMPORTANT: Do not write a placeholder output.cdr. A real CDR must be
            # created by the verified Corel Design API on Windows/CorelDRAW.
            cdr_request = {
                "status": "NOT_GENERATED_REQUIRES_REAL_COREL_API",
                "design_path": str(design_path),
                "corel_operations_path": str(operations_path),
                "requested_output_name": "output.cdr",
                "real_cdr_verified": False,
            }
            (candidate_dir / "cdr_request.json").write_text(
                json.dumps(cdr_request, indent=2), encoding="utf-8"
            )

            anonymous_id = f"REAL_GOLD_{candidate_counter:03d}"
            candidate_counter += 1
            metadata = {
                "anonymous_id": anonymous_id,
                "grammar_id": grammar.grammar_id,
                "source_design_id": source_reference["source_design_id"],
                "source_sha256": source_reference["source_sha256"],
                "category": brief.category,
                "brief_id": brief.brief_id,
                "candidate_index": candidate_index + 1,
                "design_path": str(design_path),
                "preview_path": str(preview_path),
                "corel_operations_path": str(operations_path),
                "cdr_path": None,
                "cdr_status": cdr_request["status"],
                "real_cdr_verified": False,
                "content_sha256": hashlib.sha256(preview_path.read_bytes()).hexdigest(),
                "adaptation": adaptation_report,
            }
            (candidate_dir / "metrics.json").write_text(
                json.dumps(metadata, indent=2), encoding="utf-8"
            )
            provenance = {
                "benchmark_sample_data": True,
                "customer_provided": False,
                "license_class": GENPOSTER_LICENSE_CLASS,
                "commercial_allowed": GENPOSTER_COMMERCIAL_ALLOWED,
                "project_owned": False,
                "extracted_from_real_design": True,
                "human_approved_source": True,
                "source_sha256": source_reference["source_sha256"],
                "real_cdr_verified": False,
            }
            (candidate_dir / "provenance.json").write_text(
                json.dumps(provenance, indent=2), encoding="utf-8"
            )
            all_candidates.append(metadata)

    _create_real_source_contact_sheet(inventory, output_root)
    _create_real_adaptation_contact_sheet(all_candidates, baseline_candidates, output_root)

    audit = _perform_provenance_audit(all_candidates, inventory, output_root)
    if audit["conclusion"] != "REAL_REFERENCE_STRUCTURE_PROVENANCE_VERIFIED":
        return {
            "status": "REAL_GOLD_PIPELINE_BLOCKED",
            "conclusion": audit["conclusion"],
            "audit": audit,
            "pilot_generated": False,
            "commercial_allowed": False,
        }

    baseline_claim_ready = bool(baseline_candidates) and all(
        candidate["eligible_for_human_baseline_claim"] for candidate in baseline_candidates
    )
    return {
        "status": "STABILIZED_RESEARCH_PILOT_READY",
        "conclusion": "REAL_REFERENCE_STRUCTURE_PROVENANCE_VERIFIED",
        "pilot_generated": True,
        "total_real_gold_candidates": len(all_candidates),
        "total_baseline_candidates": len(baseline_candidates),
        "categories_processed": ["SALE", "SPA"],
        "source_human_approval_verified": True,
        "real_cdr_verified": False,
        "cdr_export_required": True,
        "baseline_claim_ready": baseline_claim_ready,
        "human_comparison_queue_created": False,
        "commercial_allowed": False,
        "audit": audit,
    }


def _perform_provenance_audit(
    candidates: list[dict[str, Any]],
    inventory: dict[str, Any],
    output_dir: Path,
) -> dict[str, Any]:
    inventory_by_id = {entry["source_id"]: entry for entry in inventory.get("sources", [])}
    audit_rows: list[dict[str, Any]] = []
    all_valid = True

    for candidate in candidates:
        source_id = candidate.get("source_design_id")
        inventory_entry = inventory_by_id.get(source_id)
        source_exists = inventory_entry is not None
        source_hash = candidate.get("source_sha256")
        hash_matches_inventory = bool(
            source_exists and source_hash and source_hash == inventory_entry.get("sha256")
        )
        human_approved = bool(
            source_exists and inventory_entry.get("human_quality_status") == "APPROVED"
        )
        rights_fail_closed = bool(
            source_exists
            and inventory_entry.get("license_class") == GENPOSTER_LICENSE_CLASS
            and inventory_entry.get("commercial_allowed") is False
            and inventory_entry.get("project_owned") is False
        )
        no_fake_cdr = candidate.get("cdr_path") is None and candidate.get("real_cdr_verified") is False

        valid = source_exists and hash_matches_inventory and human_approved and rights_fail_closed and no_fake_cdr
        all_valid = all_valid and valid
        audit_rows.append(
            {
                "anonymous_id": candidate.get("anonymous_id"),
                "source_design_id": source_id,
                "real_source_inventory_entry_exists": source_exists,
                "source_hash_matches_inventory": hash_matches_inventory,
                "human_source_approval_verified": human_approved,
                "research_rights_fail_closed": rights_fail_closed,
                "fake_cdr_absent": no_fake_cdr,
                "real_cdr_verified": False,
                "business_content_leakage_check": "NOT_CLAIMED_BY_THIS_AUDIT",
                "valid": valid,
            }
        )

    conclusion = (
        "REAL_REFERENCE_STRUCTURE_PROVENANCE_VERIFIED"
        if all_valid
        else "REAL_REFERENCE_STRUCTURE_PROVENANCE_BLOCKED"
    )
    report = {
        "schema_version": "2.0",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "conclusion": conclusion,
        "total_candidates_audited": len(candidates),
        "all_candidates_valid": all_valid,
        "real_cdr_verified": False,
        "commercial_allowed": False,
        "scope": "source approval/hash/rights/no-fake-cdr only",
        "candidates": audit_rows,
    }
    (output_dir / "REAL_GOLD_PROVENANCE_AUDIT.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    return report


def _create_real_source_contact_sheet(inventory: dict[str, Any], output_dir: Path) -> None:
    sources = inventory.get("sources", [])
    if not sources:
        return
    cols = min(5, len(sources))
    rows = (len(sources) + cols - 1) // cols
    tile_w, tile_h = 280, 390
    sheet = Image.new("RGB", (cols * tile_w, rows * tile_h), "#0F172A")
    draw = ImageDraw.Draw(sheet)

    for idx, source in enumerate(sources):
        row, col = divmod(idx, cols)
        x, y = col * tile_w, row * tile_h
        preview_path = Path(source["path"]) / "source_preview.png"
        if preview_path.exists():
            with Image.open(preview_path) as raw:
                image = raw.convert("RGB")
                image.thumbnail((tile_w - 20, tile_h - 60))
                sheet.paste(image, (x + 10, y + 10))
        draw.rectangle([x + 10, y + tile_h - 45, x + tile_w - 10, y + tile_h - 10], fill="#1E293B")
        draw.text((x + 15, y + tile_h - 40), f"SOURCE: {source['source_id']}", fill="#38BDF8")
        draw.text((x + 15, y + tile_h - 24), f"CAT: {source['category']} APPROVED", fill="#94A3B8")

    sheet.save(output_dir / "real_gold_source_contact_sheet.png")


def _create_real_adaptation_contact_sheet(
    real_candidates: list[dict[str, Any]],
    baseline_candidates: list[dict[str, Any]],
    output_dir: Path,
) -> None:
    if real_candidates:
        cols = 4
        rows = (len(real_candidates) + cols - 1) // cols
        tile_w, tile_h = 280, 390
        sheet = Image.new("RGB", (cols * tile_w, rows * tile_h), "#0F172A")
        draw = ImageDraw.Draw(sheet)
        for idx, candidate in enumerate(real_candidates):
            row, col = divmod(idx, cols)
            x, y = col * tile_w, row * tile_h
            with Image.open(candidate["preview_path"]) as raw:
                image = raw.convert("RGB")
                image.thumbnail((tile_w - 20, tile_h - 60))
                sheet.paste(image, (x + 10, y + 10))
            draw.rectangle([x + 10, y + tile_h - 45, x + tile_w - 10, y + tile_h - 10], fill="#1E293B")
            draw.text((x + 15, y + tile_h - 40), f"{candidate['anonymous_id']} ({candidate['category']})", fill="#38BDF8")
            draw.text((x + 15, y + tile_h - 24), f"SRC: {candidate['source_design_id']}", fill="#94A3B8")
        sheet.save(output_dir / "real_gold_adaptation_contact_sheet.png")

    # A baseline sheet is informational only. Fixture planners are explicitly labeled.
    if baseline_candidates:
        tile_w, tile_h = 280, 390
        cols = len(baseline_candidates)
        sheet = Image.new("RGB", (cols * tile_w, 2 * tile_h), "#020617")
        draw = ImageDraw.Draw(sheet)
        for col, baseline in enumerate(baseline_candidates):
            x, y = col * tile_w, 0
            with Image.open(baseline["preview_path"]) as raw:
                image = raw.convert("RGB")
                image.thumbnail((tile_w - 20, tile_h - 60))
                sheet.paste(image, (x + 10, y + 10))
            draw.text(
                (x + 15, y + tile_h - 35),
                f"BASELINE {baseline['planner_name']} [{baseline['planner_type']}]",
                fill="#F43F5E",
            )
            gold = next(
                (candidate for candidate in real_candidates if candidate["category"] == baseline["category"]),
                None,
            )
            if gold:
                y = tile_h
                with Image.open(gold["preview_path"]) as raw:
                    image = raw.convert("RGB")
                    image.thumbnail((tile_w - 20, tile_h - 60))
                    sheet.paste(image, (x + 10, y + 10))
                draw.text((x + 15, y + tile_h - 35), f"ADAPTED {gold['source_design_id']}", fill="#10B981")
        sheet.save(output_dir / "baseline_vs_real_gold.png")
