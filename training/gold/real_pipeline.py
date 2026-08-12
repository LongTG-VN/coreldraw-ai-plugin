"""Real-reference Gold Grammar extraction with fail-closed provenance.

This module intentionally separates *source discovery* from *source approval*.
Dataset rows are never promoted to Gold references by keyword heuristics. A source
must be listed in an explicit human-curated approval manifest before extraction.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from training.gold.extractor import GoldGrammarExtractor
from training.inference.preview import render_preview
from training.schemas.design import (
    BoundingBox,
    CanvasSpec,
    ColorSpec,
    DesignDocument,
    DesignElement,
    SourceSpec,
    TextSpec,
    VisualSpec,
    normalize_bbox,
)
from training.schemas.gold import GoldDesignGrammarV1


REAL_GOLD_DIR = Path("training/data/gold_designs/real_v1")
DEFAULT_DATASET_PATH = Path("training/data/research/genposter_smoke_100/train.jsonl")
DEFAULT_APPROVED_MANIFEST_PATH = Path("training/data/gold_designs/approved_sources_v1.json")

# GenPoster100K is research-only in this project. Never widen these values from
# a filename, local copy, or project ingestion step.
GENPOSTER_LICENSE_CLASS = "CC-BY-NC-4.0"
GENPOSTER_COMMERCIAL_ALLOWED = False
GENPOSTER_PROJECT_OWNED = False


class GoldSourceApprovalRequired(RuntimeError):
    """Raised when a real-reference extraction is attempted without human-approved IDs."""


class GoldSourceManifestError(ValueError):
    """Raised when an approval manifest is malformed or references missing source IDs."""


def discover_source_candidates(
    dataset_path: Path = DEFAULT_DATASET_PATH,
    *,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Return a neutral inventory for human curation without assigning Gold categories.

    This function deliberately does not classify SALE/SPA or mark anything approved.
    It exists only to make a review manifest easier to prepare.
    """
    if not dataset_path.exists():
        raise FileNotFoundError(f"Research dataset file not found: {dataset_path}")

    candidates: list[dict[str, Any]] = []
    with dataset_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            entry = json.loads(line)
            sample_id = str(entry.get("sample_id") or "").strip()
            elements = entry.get("elements", [])
            if not sample_id or not isinstance(elements, list) or not elements:
                continue

            text_parts = [
                str(elem.get("text", {}).get("content", "")).strip()
                for elem in elements
                if isinstance(elem, dict) and isinstance(elem.get("text"), dict)
            ]
            excerpt = " | ".join(part for part in text_parts if part)[:300]
            candidates.append(
                {
                    "upstream_id": sample_id,
                    "element_count": len(elements),
                    "text_excerpt": excerpt,
                    "human_quality_status": "UNREVIEWED",
                    "approved": False,
                }
            )
            if limit is not None and len(candidates) >= limit:
                break
    return candidates


def _load_approved_manifest(manifest_path: Path) -> list[dict[str, Any]]:
    if not manifest_path.exists():
        raise GoldSourceApprovalRequired(
            "Approved Gold source manifest is missing. Review source previews first and "
            f"create an explicit manifest at: {manifest_path}"
        )

    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    rows = payload.get("sources") if isinstance(payload, dict) else None
    if not isinstance(rows, list) or not rows:
        raise GoldSourceManifestError("approval manifest must contain a non-empty 'sources' list")

    validated: list[dict[str, Any]] = []
    seen_source_ids: set[str] = set()
    seen_upstream_ids: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise GoldSourceManifestError("each approved source entry must be an object")
        source_id = str(row.get("source_id") or "").strip()
        upstream_id = str(row.get("upstream_id") or "").strip()
        category = str(row.get("category") or "").upper().strip()
        quality = str(row.get("human_quality_status") or "").upper().strip()
        approved = bool(row.get("approved", False))

        if not source_id or not upstream_id:
            raise GoldSourceManifestError("source_id and upstream_id are required")
        if category not in {"SALE", "SPA", "CAFE", "MENU", "SIGNAGE"}:
            raise GoldSourceManifestError(f"unsupported Gold category: {category!r}")
        if not approved or quality != "APPROVED":
            raise GoldSourceApprovalRequired(
                f"source {source_id!r} is not explicitly human-approved"
            )
        if source_id in seen_source_ids or upstream_id in seen_upstream_ids:
            raise GoldSourceManifestError("duplicate source_id or upstream_id in approval manifest")

        seen_source_ids.add(source_id)
        seen_upstream_ids.add(upstream_id)
        validated.append(
            {
                "source_id": source_id,
                "upstream_id": upstream_id,
                "category": category,
                "human_quality_status": "APPROVED",
                "approved": True,
                "review_notes": str(row.get("review_notes") or ""),
            }
        )
    return validated


def load_real_sources_from_dataset(
    dataset_path: Path = DEFAULT_DATASET_PATH,
    approved_manifest_path: Path = DEFAULT_APPROVED_MANIFEST_PATH,
) -> dict[str, list[tuple[str, dict[str, Any], dict[str, Any]]]]:
    """Load only exact upstream IDs from an explicit human-approved manifest."""
    if not dataset_path.exists():
        raise FileNotFoundError(f"Research dataset file not found: {dataset_path}")

    approved_rows = _load_approved_manifest(approved_manifest_path)
    approved_by_upstream = {row["upstream_id"]: row for row in approved_rows}
    found: dict[str, dict[str, Any]] = {}

    with dataset_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            entry = json.loads(line)
            upstream_id = str(entry.get("sample_id") or "").strip()
            if upstream_id in approved_by_upstream:
                found[upstream_id] = entry

    missing = sorted(set(approved_by_upstream) - set(found))
    if missing:
        raise GoldSourceManifestError(
            "approved manifest references dataset IDs that were not found: " + ", ".join(missing)
        )

    grouped: dict[str, list[tuple[str, dict[str, Any], dict[str, Any]]]] = {}
    for row in approved_rows:
        grouped.setdefault(row["category"], []).append(
            (row["source_id"], found[row["upstream_id"]], row)
        )
    return grouped


def _source_sha256(entry: dict[str, Any]) -> str:
    canonical = json.dumps(entry, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def convert_entry_to_design_document(
    source_id: str,
    category: str,
    entry: dict[str, Any],
) -> tuple[DesignDocument, str]:
    """Convert an approved dataset row to ``DesignDocument`` without widening rights."""
    source_sha256 = _source_sha256(entry)

    canvas_raw = entry.get("canvas", {})
    width = float(canvas_raw.get("width", 1080.0))
    height = float(canvas_raw.get("height", 1080.0))
    canvas = CanvasSpec(
        width=width,
        height=height,
        unit="px",
        background=VisualSpec(fill=ColorSpec(model="hex", values=["#FFFFFF"])),
    )

    elements: list[DesignElement] = []
    for idx, elem_raw in enumerate(entry.get("elements", [])):
        if not isinstance(elem_raw, dict):
            continue
        bbox_raw = elem_raw.get("bbox", {})
        if not isinstance(bbox_raw, dict):
            continue
        bbox = BoundingBox(
            x=max(0.0, float(bbox_raw.get("x", 0))),
            y=max(0.0, float(bbox_raw.get("y", 0))),
            width=max(1e-6, float(bbox_raw.get("width", 100))),
            height=max(1e-6, float(bbox_raw.get("height", 50))),
        )
        # Out-of-canvas source geometry is evidence of a bad/unsupported source,
        # not something to silently normalize into a valid Gold reference.
        if bbox.x + bbox.width > width or bbox.y + bbox.height > height:
            raise ValueError(
                f"source {source_id} element {idx} exceeds canvas; source must be reviewed/fixed"
            )

        text_spec = None
        text_raw = elem_raw.get("text")
        if isinstance(text_raw, dict) and text_raw.get("content"):
            alignment = str(text_raw.get("alignment") or "center").lower()
            if alignment not in {"left", "center", "right", "justify"}:
                alignment = "center"
            family = str(text_raw.get("font_family") or "Arial")
            text_spec = TextSpec(
                content=str(text_raw.get("content") or ""),
                font_family=family,
                font_size=max(1.0, float(text_raw.get("font_size", 24.0))),
                font_weight="bold" if "bold" in family.lower() else "normal",
                alignment=alignment,
            )

        raw_type = str(elem_raw.get("type") or "text")
        element_type = raw_type if raw_type in {"text", "rectangle", "ellipse", "group", "other"} else "other"
        if element_type == "text" and text_spec is None:
            element_type = "other"

        elements.append(
            DesignElement(
                id=f"src_elem_{idx}",
                name=str(elem_raw.get("name") or f"Element {idx}"),
                type=element_type,
                bbox=bbox,
                bbox_norm=normalize_bbox(bbox, canvas),
                rotation=float(elem_raw.get("rotation", 0.0) or 0.0),
                z_index=int(elem_raw.get("z_index", idx)),
                text=text_spec if element_type == "text" else None,
                visual=VisualSpec(fill=ColorSpec(model="hex", values=["#1E293B"])),
            )
        )

    doc = DesignDocument(
        sample_id=source_id,
        source=SourceSpec(
            name="genposter100k",
            split="train",
            license_class=GENPOSTER_LICENSE_CLASS,
            upstream_id=str(entry.get("sample_id")),
            commercial_allowed=GENPOSTER_COMMERCIAL_ALLOWED,
        ),
        canvas=canvas,
        category=category.upper(),
        elements=elements,
        metadata={"project_owned": GENPOSTER_PROJECT_OWNED},
    )
    return doc, source_sha256


def build_real_gold_library(
    output_dir: Path = REAL_GOLD_DIR,
    *,
    dataset_path: Path = DEFAULT_DATASET_PATH,
    approved_manifest_path: Path = DEFAULT_APPROVED_MANIFEST_PATH,
) -> tuple[list[GoldDesignGrammarV1], dict[str, Any]]:
    """Extract grammars only from human-approved, exact source IDs."""
    output_dir.mkdir(parents=True, exist_ok=True)
    sources_by_category = load_real_sources_from_dataset(dataset_path, approved_manifest_path)
    extractor = GoldGrammarExtractor()

    grammars: list[GoldDesignGrammarV1] = []
    inventory_entries: list[dict[str, Any]] = []

    for category, sources in sources_by_category.items():
        category_dir = output_dir / category.lower()
        category_dir.mkdir(parents=True, exist_ok=True)

        for source_id, entry, approval in sources:
            source_dir = category_dir / source_id
            source_dir.mkdir(parents=True, exist_ok=True)
            document, source_sha256 = convert_entry_to_design_document(source_id, category, entry)

            source_entry_path = source_dir / "source_entry.json"
            source_entry_path.write_text(
                json.dumps(entry, ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8",
            )

            preview_path = source_dir / "source_preview.png"
            render_preview(document, preview_path, max_dimension=800)

            grammar = extractor.extract(
                document,
                grammar_id=f"gold_{source_id}",
                grammar_name=f"Extracted {category} {source_id.upper()}",
            )
            grammar.gold_status = "PROVISIONAL_REAL_REFERENCE"
            grammar.provenance.update(
                {
                    "extracted_from_real_design": True,
                    "source_design_id": source_id,
                    "source_sha256": source_sha256,
                    "license_class": GENPOSTER_LICENSE_CLASS,
                    "commercial_allowed": GENPOSTER_COMMERCIAL_ALLOWED,
                    "project_owned": GENPOSTER_PROJECT_OWNED,
                    "human_quality_status": approval["human_quality_status"],
                    "human_approved": True,
                    "extraction_method": "GoldGrammarExtractor",
                    "extracted_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                }
            )

            (source_dir / "grammar.json").write_text(grammar.model_dump_json(indent=2), encoding="utf-8")
            source_manifest = {
                "source_id": source_id,
                "upstream_id": approval["upstream_id"],
                "category": category,
                "format": "json",
                "editable": True,
                "source_sha256": source_sha256,
                "license_class": GENPOSTER_LICENSE_CLASS,
                "commercial_allowed": GENPOSTER_COMMERCIAL_ALLOWED,
                "project_owned": GENPOSTER_PROJECT_OWNED,
                "human_quality_status": approval["human_quality_status"],
                "human_approved": True,
                "preview_path": str(preview_path),
                "source_entry_path": str(source_entry_path),
            }
            (source_dir / "source_manifest.json").write_text(
                json.dumps(source_manifest, indent=2), encoding="utf-8"
            )
            extraction_report = {
                "source_id": source_id,
                "source_sha256": source_sha256,
                "extractor_version": "1.1",
                "extracted_slot_count": len(grammar.slots),
                "extracted_relationship_count": len(grammar.relationships),
                "normalized_bounding_boxes": [slot.bbox_norm.model_dump() for slot in grammar.slots],
                "spatial_relationships": [rel.model_dump() for rel in grammar.relationships],
            }
            (source_dir / "extraction_report.json").write_text(
                json.dumps(extraction_report, indent=2), encoding="utf-8"
            )

            grammars.append(grammar)
            inventory_entries.append(
                {
                    "source_id": source_id,
                    "path": str(source_dir),
                    "category": category,
                    "format": "json",
                    "editable": True,
                    "preview_available": True,
                    "project_owned": GENPOSTER_PROJECT_OWNED,
                    "license_class": GENPOSTER_LICENSE_CLASS,
                    "commercial_allowed": GENPOSTER_COMMERCIAL_ALLOWED,
                    "human_quality_status": approval["human_quality_status"],
                    "eligible_for_extraction": True,
                    "reason": "Explicit human-approved source ID from research dataset",
                    "sha256": source_sha256,
                }
            )

    inventory = {
        "schema_version": "1.1",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_sources": len(inventory_entries),
        "source_policy": "explicit_human_approved_manifest_only",
        "commercial_allowed": False,
        "sources": inventory_entries,
    }
    for category in {entry["category"] for entry in inventory_entries}:
        inventory[f"{category.lower()}_source_count"] = sum(
            1 for entry in inventory_entries if entry["category"] == category
        )

    (output_dir / "source_inventory.json").write_text(
        json.dumps(inventory, indent=2), encoding="utf-8"
    )
    return grammars, inventory
