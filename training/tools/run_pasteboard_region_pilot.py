"""Analyze and render the fixed five-source pasteboard region pilot."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from training.company_archive.extractor import inspection_to_design_document
from training.company_archive.gold_pilot import assess_roundtrip_support, extraction_coverage
from training.company_archive.hashing import sha256_file
from training.company_archive.inspector import CompanyCdrInspector
from training.company_archive.models import CdrInspectionV1
from training.company_archive.region_artifacts import (
    build_region_contact_sheet,
    label_region_preview,
    write_region_manifest,
)
from training.company_archive.regions import analyze_design_regions
from training.company_archive.safety import assert_source_unchanged, source_stat_guard


FIXED_IDS = (
    "CDR_000159",
    "CDR_000020",
    "CDR_000401",
    "CDR_000442",
    "CDR_000295",
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-pilot-root",
        type=Path,
        default=Path("training/workspace/company_archive/gold_source_pilot"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("training/workspace/company_archive/pasteboard_gold_pilot"),
    )
    parser.add_argument("--analyze-only", action="store_true")
    parser.add_argument(
        "--refresh-inspection",
        action="store_true",
        help="Reinspect each source copy through real Corel before region analysis.",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    source_root = args.source_pilot_root.resolve(strict=True)
    output_root = args.output.resolve(strict=False)
    output_root.mkdir(parents=True, exist_ok=True)
    inspector = CompanyCdrInspector()
    all_labeled: list[Path] = []
    source_reports: list[dict[str, object]] = []

    for design_id in FIXED_IDS:
        source_dir = source_root / design_id
        inspection_path = source_dir / "source_inspection.json"
        source_copy = source_dir / "source_copy.cdr"
        guard = source_stat_guard(source_copy)
        digest = sha256_file(source_copy)
        if args.refresh_inspection:
            inspection = inspector.inspect(source_copy, archive_root=source_root)
            refreshed_path = output_root / design_id / "source_inspection.json"
            refreshed_path.parent.mkdir(parents=True, exist_ok=True)
            refreshed_path.write_text(
                json.dumps(inspection.model_dump(mode="json"), ensure_ascii=False, indent=2)
                + "\n",
                encoding="utf-8",
            )
        else:
            inspection = CdrInspectionV1.model_validate_json(
                inspection_path.read_text(encoding="utf-8")
            )
        analysis = analyze_design_regions(inspection, design_id=design_id)
        design_output = output_root / design_id
        raw_output = design_output / "raw"
        labeled_output = design_output / "regions"
        preview_paths: dict[str, Path] = {}
        errors: dict[str, str] = {}
        labeled_paths: list[Path] = []

        if not args.analyze_only:
            for region in analysis.candidate_regions:
                raw_path = raw_output / f"{region.region_id}.png"
                labeled_path = labeled_output / f"{region.region_id}.png"
                try:
                    if not raw_path.is_file() or raw_path.stat().st_size == 0:
                        if region.method == "ACTIVE_PAGE":
                            inspector.render_preview(
                                source_copy,
                                raw_path,
                                archive_root=source_root,
                            )
                        else:
                            inspector.render_region_preview(
                                source_copy,
                                raw_path,
                                archive_root=source_root,
                                region=region,
                            )
                    label_region_preview(
                        raw_path,
                        labeled_path,
                        design_id=design_id,
                        region_id=region.region_id,
                    )
                    preview_paths[region.region_id] = labeled_path
                    labeled_paths.append(labeled_path)
                    all_labeled.append(labeled_path)
                except Exception as exc:  # real Corel evidence is persisted per region
                    errors[region.region_id] = f"{type(exc).__name__}: {exc}"

        write_region_manifest(
            analysis,
            design_output / "region_manifest.json",
            preview_paths=preview_paths,
            errors=errors,
        )
        if labeled_paths:
            build_region_contact_sheet(
                labeled_paths,
                design_output / "region_contact_sheet.png",
            )

        document_status = "BLOCKED_REGION_SELECTION"
        roundtrip: dict[str, object] = {
            "status": "NOT_ATTEMPTED_REGION_SELECTION_REQUIRED"
        }
        coverage: dict[str, object] | None = None
        selected = analysis.selected_region()
        if selected is not None:
            try:
                document = inspection_to_design_document(
                    inspection,
                    source_sha256=digest,
                    category="OTHER",
                    region=selected,
                )
                document_path = design_output / "design.json"
                document_path.write_text(
                    json.dumps(document.model_dump(mode="json"), ensure_ascii=False, indent=2)
                    + "\n",
                    encoding="utf-8",
                )
                coverage = extraction_coverage(document)
                roundtrip = assess_roundtrip_support(document)
                document_status = "VALID"
            except Exception as exc:
                document_status = f"EXTRACTION_BLOCKED: {type(exc).__name__}: {exc}"
                roundtrip = {"status": "NOT_ATTEMPTED_EXTRACTION_BLOCKED"}

        assert_source_unchanged(source_copy, guard)
        source_reports.append(
            {
                "design_id": design_id,
                "object_count": inspection.object_count,
                "inside_page": sum(item.inside_page for item in analysis.objects),
                "outside_page": sum(item.outside_page for item in analysis.objects),
                "candidate_region_count": len(analysis.candidate_regions),
                "spatial_cluster_count": analysis.spatial_cluster_count,
                "selected_region": analysis.selected_region_id,
                "selection_method": analysis.selection_method,
                "selection_confidence": analysis.selection_confidence,
                "analysis_status": analysis.status,
                "preview_count": len(preview_paths),
                "preview_errors": errors,
                "design_document_status": document_status,
                "extraction_coverage": coverage,
                "roundtrip": roundtrip,
                "source_copy_unchanged": True,
            }
        )

    if all_labeled:
        build_region_contact_sheet(
            all_labeled,
            output_root / "pasteboard_region_contact_sheet_all.png",
        )
    summary = {
        "schema_version": "1.0",
        "fixed_source_count": len(FIXED_IDS),
        "sources": source_reports,
        "region_selection_required": sum(
            item["analysis_status"] == "REGION_SELECTION_REQUIRED"
            for item in source_reports
        ),
        "source_mutations_detected": 0,
        "qwen_used": False,
        "antigravity_used": False,
        "training_run": False,
    }
    (output_root / "PILOT_SUMMARY.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
