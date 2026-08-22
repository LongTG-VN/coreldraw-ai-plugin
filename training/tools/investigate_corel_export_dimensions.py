"""Reproduce Corel current-page PNG dimension variance without mutating sources."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from PIL import Image

from corel_bridge import corel_bridge
from extended_bridge import CDR_CURRENT_PAGE, CDR_PNG, CDR_RGB_COLOR_IMAGE
from training.company_archive.database import ArchiveDatabase
from training.company_archive.hashing import sha256_file
from training.company_archive.inspector import CompanyCdrInspector, bounded_export_size
from training.company_archive.safety import assert_source_unchanged, source_stat_guard
from training.corel_operator.policy import source_token
from training.corel_operator.state import OperatorStateDatabase


def _image_evidence(path: Path) -> dict[str, Any]:
    with Image.open(path) as image:
        width, height = image.size
    return {
        "width": width,
        "height": height,
        "size_bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def _artwork_bounds(inspection: Any) -> dict[str, float] | None:
    boxes = [item.bbox for item in inspection.objects]
    if not boxes:
        return None
    left = min(float(box["x"]) for box in boxes)
    top = min(float(box["y"]) for box in boxes)
    right = max(float(box["x"]) + float(box["width"]) for box in boxes)
    bottom = max(float(box["y"]) + float(box["height"]) for box in boxes)
    return {
        "x": left,
        "y": top,
        "width": right - left,
        "height": bottom - top,
    }


def _selected_object(inspection: Any, object_id: str | None) -> dict[str, Any] | None:
    if not object_id:
        return None
    for item in inspection.objects:
        if item.object_id == object_id:
            return {
                "object_id": item.object_id,
                "object_type": item.object_type,
                "bbox": item.bbox,
                "font_size": item.font_size,
                "parent_id": item.parent_id,
                "locked": bool(item.metadata.get("locked", False)),
            }
    return None


def _export_current_page(
    document_path: Path,
    output_path: Path,
    *,
    maintain_aspect: bool,
    dpi: int,
    max_dimension: int,
    max_pixels: int,
    immutable_source: bool,
) -> dict[str, Any]:
    inspector = CompanyCdrInspector()
    guard = source_stat_guard(document_path)
    source_hash_before = sha256_file(document_path) if immutable_source else None
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        output_path.unlink()
    try:
        with corel_bridge.session() as (application, active_document):
            active_path = str(getattr(active_document, "FullFileName", "") or "")
            if active_path and Path(active_path).resolve() == document_path.resolve():
                raise RuntimeError("diagnostic document is already active")
            opened = inspector._open_document(application, document_path.resolve())
            try:
                page = opened.ActivePage
                page_width = float(page.SizeWidth)
                page_height = float(page.SizeHeight)
                width, height = bounded_export_size(
                    page_width,
                    page_height,
                    max_dimension=max_dimension,
                    max_pixels=max_pixels,
                )
                options = application.CreateStructExportOptions()
                palette = application.CreateStructPaletteOptions()
                options.ImageType = CDR_RGB_COLOR_IMAGE
                options.Overwrite = False
                options.ResolutionX = dpi
                options.ResolutionY = dpi
                options.MaintainAspect = maintain_aspect
                options.SizeX = width
                options.SizeY = height
                export_filter = opened.ExportEx(
                    str(output_path),
                    CDR_PNG,
                    CDR_CURRENT_PAGE,
                    options,
                    palette,
                )
                export_filter.Finish()
                page_index = int(getattr(page, "Index", 1) or 1)
            finally:
                opened.Close()
    finally:
        assert_source_unchanged(document_path, guard)
    if immutable_source and sha256_file(document_path) != source_hash_before:
        raise RuntimeError("source SHA256 changed during export investigation")
    return {
        "export_range": "cdrCurrentPage",
        "export_range_code": CDR_CURRENT_PAGE,
        "page_index": page_index,
        "dpi_x": dpi,
        "dpi_y": dpi,
        "requested_size_x": width,
        "requested_size_y": height,
        "maintain_aspect": maintain_aspect,
        "image_type": "cdrRGBColorImage",
        "image_type_code": CDR_RGB_COLOR_IMAGE,
        "anti_aliasing": "Corel default",
        "transparent": "Corel default",
        "actual": _image_evidence(output_path),
    }


def _build_token_index(database: ArchiveDatabase, archive_root: Path) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in database.rows("cdr_candidate=1"):
        path = Path(str(row["absolute_path"]))
        result[source_token(path, archive_root)] = row
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive-root", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--pilot-workspace", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run-id", default="real-mutation-pilot-001")
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--dpi", type=int, default=96)
    args = parser.parse_args()
    if not 1 <= args.limit <= 10:
        raise SystemExit("--limit must be in 1..10")
    if not 36 <= args.dpi <= 600:
        raise SystemExit("--dpi must be in 36..600")

    archive_root = args.archive_root.resolve()
    pilot_workspace = args.pilot_workspace.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    token_index = _build_token_index(ArchiveDatabase(args.inventory), archive_root)
    rows = [
        row
        for row in OperatorStateDatabase(args.state).batch_rows(args.run_id)
        if row["result"].get("result") == "NEEDS_REVIEW"
        and "PREVIEW_DIMENSION_CHANGED" in row["result"].get("warnings", [])
    ][: args.limit]
    evidence: list[dict[str, Any]] = []
    inspector = CompanyCdrInspector()
    source_mutations = 0
    for index, state_row in enumerate(rows, start=1):
        result = state_row["result"]
        token = str(result["source_token"])
        inventory_row = token_index[token]
        source = Path(str(inventory_row["absolute_path"])).resolve()
        working_copy = Path(str(result["working_copy"])).resolve()
        try:
            working_copy.relative_to(pilot_workspace)
        except ValueError as exc:
            raise RuntimeError("working copy escaped the pilot workspace") from exc
        source_guard = source_stat_guard(source)
        source_sha_before = sha256_file(source)
        source_inspection = inspector.inspect(source, archive_root=archive_root)
        working_inspection = inspector.inspect(
            working_copy,
            archive_root=working_copy.parent,
        )
        item_root = output / f"case_{index:02d}"
        legacy_source = _export_current_page(
            source,
            item_root / "source_maintain_aspect_true.png",
            maintain_aspect=True,
            dpi=args.dpi,
            max_dimension=2400,
            max_pixels=8_000_000,
            immutable_source=True,
        )
        legacy_working = _export_current_page(
            working_copy,
            item_root / "working_maintain_aspect_true.png",
            maintain_aspect=True,
            dpi=args.dpi,
            max_dimension=2400,
            max_pixels=8_000_000,
            immutable_source=False,
        )
        exact_source = _export_current_page(
            source,
            item_root / "source_maintain_aspect_false.png",
            maintain_aspect=False,
            dpi=args.dpi,
            max_dimension=2400,
            max_pixels=8_000_000,
            immutable_source=True,
        )
        exact_working = _export_current_page(
            working_copy,
            item_root / "working_maintain_aspect_false.png",
            maintain_aspect=False,
            dpi=args.dpi,
            max_dimension=2400,
            max_pixels=8_000_000,
            immutable_source=False,
        )
        source_sha_after = sha256_file(source)
        try:
            assert_source_unchanged(source, source_guard)
        except Exception:
            source_mutations += 1
            raise
        if source_sha_after != source_sha_before:
            source_mutations += 1
            raise RuntimeError("source SHA256 changed during investigation")
        target_id = (
            str(result.get("resolved_targets", [{}])[0].get("object_id"))
            if result.get("resolved_targets")
            else None
        )
        evidence.append(
            {
                "case_id": f"EXPORT_CASE_{index:02d}",
                "source_token": token,
                "operation": result.get("metadata", {})
                .get("planner", {})
                .get("operation_mode"),
                "source_safety": {
                    "size_before": source_guard[0],
                    "mtime_ns_before": source_guard[1],
                    "ctime_ns_before": source_guard[2],
                    "sha256_before": source_sha_before,
                    "sha256_after": source_sha_after,
                    "unchanged": True,
                },
                "page_before": {
                    "width": source_inspection.page_width,
                    "height": source_inspection.page_height,
                    "unit": source_inspection.unit,
                    "unit_code": source_inspection.corel_unit_code,
                    "page_count": source_inspection.page_count,
                },
                "page_after": {
                    "width": working_inspection.page_width,
                    "height": working_inspection.page_height,
                    "unit": working_inspection.unit,
                    "unit_code": working_inspection.corel_unit_code,
                    "page_count": working_inspection.page_count,
                },
                "object_count_before": source_inspection.object_count,
                "object_count_after": working_inspection.object_count,
                "artwork_bounds_before": _artwork_bounds(source_inspection),
                "artwork_bounds_after": _artwork_bounds(working_inspection),
                "target_before": _selected_object(source_inspection, target_id),
                "target_after": _selected_object(working_inspection, target_id),
                "previous_preview_before": _image_evidence(Path(result["preview_before"])),
                "previous_preview_after": _image_evidence(Path(result["preview_after"])),
                "fresh_exports": {
                    "maintain_aspect_true": {
                        "source": legacy_source,
                        "working_copy": legacy_working,
                    },
                    "maintain_aspect_false": {
                        "source": exact_source,
                        "working_copy": exact_working,
                    },
                },
            }
        )

    payload = {
        "schema_version": "1.0",
        "purpose": "diagnose Corel current-page export dimension variance",
        "case_count": len(evidence),
        "dpi": args.dpi,
        "source_mutations_detected": source_mutations,
        "cases": evidence,
    }
    report = output / "export_dimension_investigation.json"
    report.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps({"report": str(report), **payload}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
