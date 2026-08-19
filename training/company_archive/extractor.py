"""Prototype conversion from a real Corel inspection into DesignDocument."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from training.company_archive.hashing import sha256_file
from training.company_archive.inspector import CompanyCdrInspector
from training.company_archive.models import CdrInspectionV1, CdrObjectV1, RightsStatus
from training.company_archive.regions import DesignRegion
from training.company_archive.safety import resolve_source_file
from training.schemas.design import (
    BoundingBox,
    CanvasSpec,
    ColorSpec,
    DesignDocument,
    DesignElement,
    SourceSpec,
    SourceCanvasBounds,
    SourceCanvasOrigin,
    TextSpec,
    VisualSpec,
    normalize_bbox,
)


UNIT_TO_MM = {
    "tenth_micron": 0.0001,
    "in": 25.4,
    "ft": 304.8,
    "mm": 1.0,
    "cm": 10.0,
    "m": 1000.0,
    "km": 1_000_000.0,
    "pt": 25.4 / 72.0,
    "q": 0.25,
    "h": 0.25,
}


def _id(value: str, index: int) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._:-]+", "_", value).strip("_")
    if not cleaned or not cleaned[0].isalnum():
        cleaned = f"object_{index}"
    return cleaned[:180]


def _color(payload: dict[str, Any] | None) -> ColorSpec | None:
    if not payload or payload.get("model") not in {"cmyk", "hex", "rgb", "rgba"}:
        return None
    try:
        return ColorSpec.model_validate(payload)
    except ValueError:
        return None


def _alignment(value: str | None) -> str | None:
    if not value:
        return None
    lowered = value.casefold()
    for name in ("left", "center", "right", "justify"):
        if name in lowered:
            return name
    return None


class CompanyCdrExtractor:
    """Extract page-one structured objects; never mutate or save the source CDR."""

    def __init__(self, inspector: CompanyCdrInspector | None = None) -> None:
        self.inspector = inspector or CompanyCdrInspector()

    def extract(
        self,
        path: Path,
        *,
        archive_root: Path,
        category: str = "OTHER",
        rights_status: RightsStatus = RightsStatus.UNKNOWN,
        commercial_allowed: bool = False,
        inspection: CdrInspectionV1 | None = None,
        region: DesignRegion | None = None,
    ) -> tuple[DesignDocument, CdrInspectionV1]:
        source = resolve_source_file(path, archive_root, suffixes={".cdr", ".cdt"})
        if commercial_allowed and rights_status != RightsStatus.CONFIRMED_COMPANY_OWNED:
            raise ValueError("commercial permission requires explicit confirmed company rights")
        inspected = inspection or self.inspector.inspect(source, archive_root=archive_root)
        if Path(inspected.source_path).resolve() != source:
            raise ValueError("inspection provenance does not match source CDR")
        source_sha = sha256_file(source)
        document = inspection_to_design_document(
            inspected,
            source_sha256=source_sha,
            category=category,
            rights_status=rights_status,
            commercial_allowed=commercial_allowed,
            region=region,
        )
        return document, inspected


def inspection_to_design_document(
    inspection: CdrInspectionV1,
    *,
    source_sha256: str,
    category: str,
    rights_status: RightsStatus = RightsStatus.UNKNOWN,
    commercial_allowed: bool = False,
    region: DesignRegion | None = None,
) -> DesignDocument:
    if not re.fullmatch(r"[a-f0-9]{64}", source_sha256):
        raise ValueError("real CDR extraction requires a full SHA256 source binding")
    if commercial_allowed and rights_status != RightsStatus.CONFIRMED_COMPANY_OWNED:
        raise ValueError("commercial permission requires explicit confirmed company rights")

    if inspection.unit == "px":
        output_unit = "px"
        scale = 1.0
    elif inspection.unit in UNIT_TO_MM:
        output_unit = "mm"
        scale = UNIT_TO_MM[inspection.unit]
    else:
        raise ValueError(f"unsupported Corel document unit for extraction: {inspection.unit}")
    if region is None:
        width = inspection.page_width * scale
        height = inspection.page_height * scale
        canvas = CanvasSpec(width=width, height=height, unit=output_unit)
        selected_objects = list(inspection.objects)
    else:
        width = region.bounds.width * scale
        height = region.bounds.height * scale
        canvas = CanvasSpec(
            width=width,
            height=height,
            unit=output_unit,
            source_type="ARTWORK_REGION",
            source_page_bounds=SourceCanvasBounds(
                left=0,
                bottom=0,
                right=inspection.page_width * scale,
                top=inspection.page_height * scale,
            ),
            artwork_region_bounds=SourceCanvasBounds(
                left=region.bounds.left * scale,
                bottom=region.bounds.bottom * scale,
                right=region.bounds.right * scale,
                top=region.bounds.top * scale,
            ),
            normalization_origin=SourceCanvasOrigin(
                x=region.bounds.left * scale,
                y=region.bounds.bottom * scale,
            ),
        )
        selected = set(region.included_object_ids)
        selected_objects = [item for item in inspection.objects if item.object_id in selected]
        missing = selected - {item.object_id for item in selected_objects}
        if missing:
            raise ValueError(
                "region references missing inspection objects: " + ", ".join(sorted(missing))
            )

    id_map = {
        item.object_id: _id(item.object_id, index)
        for index, item in enumerate(selected_objects, start=1)
    }
    elements: list[DesignElement] = []
    for index, item in enumerate(selected_objects, start=1):
        element = _element_from_object(
            item,
            index,
            id_map,
            canvas,
            scale,
            source_unit=inspection.unit,
            region=region,
        )
        elements.append(element)

    source_path = Path(inspection.source_path)
    sample_id = "company_cdr:" + hashlib.sha256(
        f"{source_sha256}|page:1|region:{region.region_id if region else 'active_page'}".encode("utf-8")
    ).hexdigest()[:24]
    return DesignDocument(
        sample_id=sample_id,
        source=SourceSpec(
            name="company_cdr_archive",
            split="human_curated",
            license_class=(
                "COMPANY_OWNED_CONFIRMED"
                if rights_status == RightsStatus.CONFIRMED_COMPANY_OWNED
                else "COMPANY_ARCHIVE_RIGHTS_UNVERIFIED"
            ),
            upstream_id=source_sha256,
            commercial_allowed=commercial_allowed,
        ),
        canvas=canvas,
        category=category,
        elements=elements,
        metadata={
            "source_type": (
                "COMPANY_OWNED_CDR"
                if rights_status == RightsStatus.CONFIRMED_COMPANY_OWNED
                else "COMPANY_ARCHIVE_CDR"
            ),
            "project_owned": rights_status == RightsStatus.CONFIRMED_COMPANY_OWNED,
            "rights_status": rights_status.value,
            "source_sha256": source_sha256,
            "source_filename": source_path.name,
            "source_path_committed": False,
            "source_page": 1,
            "source_page_count": inspection.page_count,
            "extraction_scope": (
                "DERIVED_ARTWORK_REGION" if region else "ACTIVE_PAGE_ONLY_PROTOTYPE"
            ),
            "source_page_bounds": {
                "left": 0.0,
                "bottom": 0.0,
                "right": inspection.page_width,
                "top": inspection.page_height,
            },
            "design_region": region.model_dump(mode="json") if region else None,
            "source_save_called": inspection.source_save_called,
            "bitmap_reconstruction_supported": False,
        },
    )


def _element_from_object(
    item: CdrObjectV1,
    index: int,
    id_map: dict[str, str],
    canvas: CanvasSpec,
    scale: float,
    *,
    source_unit: str,
    region: DesignRegion | None = None,
) -> DesignElement:
    if region is None and item.metadata.get("bbox_clipped_to_page") is True:
        raise ValueError(
            f"Corel object lies outside the active page and cannot be normalized: "
            f"{item.corel_name}"
        )
    source_raw = item.metadata.get("source_raw_bbox")
    if region is not None:
        if not isinstance(source_raw, dict):
            raise ValueError(f"Corel object lacks source geometry: {item.corel_name}")
        source_left = float(source_raw["left"])
        source_bottom = float(source_raw["bottom"])
        source_width = float(source_raw["width"])
        source_height = float(source_raw["height"])
        virtual_left = source_left - float(region.bounds.left)
        virtual_bottom = source_bottom - float(region.bounds.bottom)
        virtual_top = float(region.bounds.top) - (source_bottom + source_height)
        tolerance = 1e-6
        if (
            virtual_left < -tolerance
            or virtual_bottom < -tolerance
            or virtual_top < -tolerance
            or virtual_left + source_width > region.bounds.width + tolerance
            or virtual_bottom + source_height > region.bounds.height + tolerance
        ):
            raise ValueError(f"Corel object exceeds selected design region: {item.corel_name}")
        raw = {
            "x": max(0.0, virtual_left),
            "y": max(0.0, virtual_top),
            "width": source_width,
            "height": source_height,
        }
    else:
        raw = item.bbox
    bbox = BoundingBox(
        x=max(0.0, raw["x"] * scale),
        y=max(0.0, raw["y"] * scale),
        width=max(1e-9, raw["width"] * scale),
        height=max(1e-9, raw["height"] * scale),
    )
    if bbox.x + bbox.width > canvas.width + 1e-6 or bbox.y + bbox.height > canvas.height + 1e-6:
        raise ValueError(f"Corel object exceeds page bounds: {item.corel_name}")
    kind = item.object_type
    supported = kind if kind in {"text", "rectangle", "ellipse", "group"} else "other"
    text = None
    if supported == "text":
        text = TextSpec(
            content=item.text or "",
            font_family=item.font_family or "Arial",
            # Corel Text.Story.Size is expressed in typographic points and is
            # independent from the document coordinate unit.
            font_size=item.font_size,
            font_weight=item.font_weight,
            alignment=_alignment(item.alignment),
        )
    return DesignElement(
        id=id_map[item.object_id],
        name=item.corel_name,
        type=supported,
        bbox=bbox,
        bbox_norm=normalize_bbox(bbox, canvas),
        rotation=item.rotation,
        z_index=item.z_index,
        layer=item.layer or "default",
        parent_id=id_map.get(item.parent_id) if item.parent_id else None,
        text=text,
        visual=VisualSpec(fill=_color(item.fill), stroke=_color(item.stroke)),
        metadata={
            **item.metadata,
            "source_absolute_bbox": source_raw,
            "source_absolute_bbox_unit": source_unit,
            "virtual_bbox_bottom_left_norm": (
                {
                    "x": (float(source_raw["left"]) - float(region.bounds.left))
                    / region.bounds.width,
                    "y": (float(source_raw["bottom"]) - float(region.bounds.bottom))
                    / region.bounds.height,
                    "width": float(source_raw["width"]) / region.bounds.width,
                    "height": float(source_raw["height"]) / region.bounds.height,
                }
                if region is not None and isinstance(source_raw, dict)
                else None
            ),
            "source_object_type": item.object_type,
            "source_corel_name": item.corel_name,
            "reconstructable_by_current_compiler": supported != "other",
        },
    )
