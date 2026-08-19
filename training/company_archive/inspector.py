"""Read-only-by-policy Corel inspector for explicitly selected CDR files."""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

from corel_bridge import CorelDrawBridge, CorelDrawBridgeError, corel_bridge
from extended_bridge import CDR_CURRENT_PAGE, CDR_PNG, CDR_RGB_COLOR_IMAGE
from training.company_archive.models import CdrInspectionV1, CdrObjectV1
from training.company_archive.regions import DesignRegion
from training.company_archive.safety import (
    assert_source_unchanged,
    resolve_source_file,
    source_stat_guard,
)


COREL_UNITS = {
    0: "tenth_micron",
    1: "in",
    2: "ft",
    3: "mm",
    4: "cm",
    5: "px",
    6: "mile",
    7: "m",
    8: "km",
    9: "didot",
    10: "agate",
    11: "yard",
    12: "pica",
    13: "cicero",
    14: "pt",
    15: "q",
    16: "h",
}
CDR_SELECTION = 2


def bounded_export_size(
    page_width: float,
    page_height: float,
    *,
    max_dimension: int = 2400,
    max_pixels: int = 8_000_000,
) -> tuple[int, int]:
    """Return an aspect-preserving raster size bounded for unattended exports."""

    width = float(page_width)
    height = float(page_height)
    if not math.isfinite(width) or not math.isfinite(height) or width <= 0 or height <= 0:
        raise ValueError("Corel page dimensions must be finite and positive")
    if max_dimension < 1 or max_pixels < 1:
        raise ValueError("preview bounds must be positive")
    scale = min(
        max_dimension / width,
        max_dimension / height,
        math.sqrt(max_pixels / (width * height)),
    )
    return max(1, int(round(width * scale))), max(1, int(round(height * scale)))


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _bool(value: Any, default: bool | None = None) -> bool | None:
    try:
        return bool(value)
    except Exception:
        return default


def _attribute(value: Any, name: str, default: Any = None) -> Any:
    try:
        return getattr(value, name)
    except Exception:
        return default


def _collection_items(collection: Any):
    try:
        for item in collection:
            yield item
        return
    except Exception:
        pass
    count = int(getattr(collection, "Count", 0) or 0)
    for index in range(1, count + 1):
        try:
            yield collection.Item(index)
        except Exception:
            yield collection(index)


def _safe_name(value: str, index: int) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._:-]+", "_", value.strip()).strip("_")
    if not cleaned or not cleaned[0].isalnum():
        cleaned = f"object_{index}"
    return cleaned[:160]


def _shape_text(shape: Any) -> tuple[str | None, str | None, float | None, str | None]:
    try:
        story = shape.Text.Story
        text = str(getattr(story, "Text", story))
        font = str(story.Font) if getattr(story, "Font", None) else None
        size = _float(getattr(story, "Size", None), 0) or None
        alignment = str(getattr(story, "Alignment", "")) or None
        return text, font, size, alignment
    except Exception:
        return None, None, None, None


def _shape_color(shape: Any) -> dict[str, Any] | None:
    try:
        color = shape.Fill.UniformColor
        return {
            "model": "cmyk",
            "values": [
                _float(color.CMYKCyan),
                _float(color.CMYKMagenta),
                _float(color.CMYKYellow),
                _float(color.CMYKBlack),
            ],
        }
    except Exception:
        return None


def _shape_kind(shape: Any, text: str | None, child_count: int) -> str:
    type_code = int(getattr(shape, "Type", 0) or 0)
    if text is not None:
        return "text"
    if child_count:
        return "group"
    if type_code == 4:
        return "image"
    if type_code == 1:
        return "rectangle"
    if type_code == 2:
        return "ellipse"
    return "vector"


def _bounded_bbox(
    *,
    left: float,
    bottom: float,
    shape_width: float,
    shape_height: float,
    page_width: float,
    page_height: float,
) -> tuple[dict[str, float], dict[str, float], bool]:
    """Clamp off-page Corel geometry and retain the unclipped source evidence."""

    raw = {
        "left": left,
        "bottom": bottom,
        "width": shape_width,
        "height": shape_height,
    }
    raw_top = page_height - bottom - shape_height
    bounded_left = min(max(0.0, left), max(0.0, page_width - 1e-9))
    bounded_top = min(max(0.0, raw_top), max(0.0, page_height - 1e-9))
    bounded_width = max(1e-9, min(shape_width, page_width - bounded_left))
    bounded_height = max(1e-9, min(shape_height, page_height - bounded_top))
    bounded = {
        "x": bounded_left,
        "y": bounded_top,
        "width": bounded_width,
        "height": bounded_height,
    }
    clipped = (
        abs(bounded_left - left) > 1e-9
        or abs(bounded_top - raw_top) > 1e-9
        or abs(bounded_width - shape_width) > 1e-9
        or abs(bounded_height - shape_height) > 1e-9
    )
    return bounded, raw, clipped


class CompanyCdrInspector:
    """Open one approved CDR, inspect it, and close it without ever saving it."""

    def __init__(self, bridge: CorelDrawBridge = corel_bridge) -> None:
        self.bridge = bridge

    @staticmethod
    def _open_document(application: Any, source: Path) -> Any:
        """Open through Corel, then resolve the actual active Document COM object.

        CorelDRAW 2020 returns an ``OpenDocument`` command wrapper from
        ``Application.OpenDocument``.  The editable document is exposed through
        ``Application.ActiveDocument`` after the command completes.
        """

        application.OpenDocument(str(source))
        opened = getattr(application, "ActiveDocument", None)
        if opened is None:
            raise CorelDrawBridgeError("Corel did not expose the opened active document")
        opened_path = str(getattr(opened, "FullFileName", "") or "")
        if opened_path and Path(opened_path).resolve() != source:
            raise CorelDrawBridgeError(
                f"Corel activated a different document after open: {opened_path}"
            )
        try:
            opened.Unit = 3  # Corel cdrMillimeter; keep page and shape coordinates aligned.
        except Exception as exc:
            raise CorelDrawBridgeError(
                f"could not set opened CDR to millimetres for inspection: {exc}"
            ) from exc
        return opened

    def inspect(self, path: Path, *, archive_root: Path) -> CdrInspectionV1:
        source = resolve_source_file(path, archive_root, suffixes={".cdr", ".cdt"})
        before = source_stat_guard(source)
        try:
            with self.bridge.session() as (application, active_document):
                active_path = str(getattr(active_document, "FullFileName", "") or "")
                if active_path and Path(active_path).resolve() == source:
                    raise CorelDrawBridgeError(
                        "source CDR is already active; close it before read-only inspection"
                    )
                opened = self._open_document(application, source)
                try:
                    return self._inspect_opened(application, opened, source, before)
                finally:
                    try:
                        opened.Close()
                    except Exception as exc:
                        raise CorelDrawBridgeError(
                            f"could not close source CDR without saving: {exc}"
                        ) from exc
        finally:
            assert_source_unchanged(source, before)

    def render_preview(
        self,
        path: Path,
        output: Path,
        *,
        archive_root: Path,
        dpi: int = 96,
        max_dimension: int = 2400,
        max_pixels: int = 8_000_000,
    ) -> Path:
        source = resolve_source_file(path, archive_root, suffixes={".cdr", ".cdt"})
        target = output.expanduser().resolve(strict=False)
        if target.suffix.casefold() != ".png":
            raise ValueError("preview target must use .png")
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            raise FileExistsError(target)
        before = source_stat_guard(source)
        try:
            with self.bridge.session() as (application, active_document):
                active_path = str(getattr(active_document, "FullFileName", "") or "")
                if active_path and Path(active_path).resolve() == source:
                    raise CorelDrawBridgeError("source CDR is already active")
                opened = self._open_document(application, source)
                try:
                    page = opened.ActivePage
                    export_width, export_height = bounded_export_size(
                        _float(page.SizeWidth),
                        _float(page.SizeHeight),
                        max_dimension=max_dimension,
                        max_pixels=max_pixels,
                    )
                    options = application.CreateStructExportOptions()
                    palette = application.CreateStructPaletteOptions()
                    options.ImageType = CDR_RGB_COLOR_IMAGE
                    options.Overwrite = False
                    options.ResolutionX = dpi
                    options.ResolutionY = dpi
                    options.MaintainAspect = True
                    options.SizeX = export_width
                    options.SizeY = export_height
                    export_filter = opened.ExportEx(
                        str(target), CDR_PNG, CDR_CURRENT_PAGE, options, palette
                    )
                    export_filter.Finish()
                finally:
                    opened.Close()
        finally:
            assert_source_unchanged(source, before)
        if not target.is_file() or target.stat().st_size == 0:
            raise CorelDrawBridgeError("Corel preview export produced no file")
        return target

    @staticmethod
    def _shape_map(document: Any) -> tuple[dict[str, Any], dict[str, str | None]]:
        """Recreate the inspection's stable object-ID traversal for selection export."""

        page = document.ActivePage
        raw_shapes = list(_collection_items(getattr(page, "Shapes", page.ActiveLayer.Shapes)))
        shape_by_id: dict[str, Any] = {}
        parent_by_id: dict[str, str | None] = {}
        used_object_ids: set[str] = set()

        def visit(shape: Any, *, parent_id: str | None = None) -> None:
            index = len(shape_by_id) + 1
            raw_name = str(getattr(shape, "Name", "") or f"object_{index}")
            base_object_id = _safe_name(raw_name, index)
            object_id = base_object_id
            suffix = 2
            while object_id in used_object_ids:
                object_id = f"{base_object_id}_{suffix}"
                suffix += 1
            used_object_ids.add(object_id)
            shape_by_id[object_id] = shape
            parent_by_id[object_id] = parent_id
            for child in _collection_items(getattr(shape, "Shapes", [])):
                visit(child, parent_id=object_id)

        for shape in raw_shapes:
            visit(shape)
        return shape_by_id, parent_by_id

    def render_region_preview(
        self,
        path: Path,
        output: Path,
        *,
        archive_root: Path,
        region: DesignRegion,
        dpi: int = 96,
        max_dimension: int = 2400,
        max_pixels: int = 8_000_000,
    ) -> Path:
        """Export selected source-copy shapes without moving or saving them."""

        if region.source_page != 1:
            raise ValueError("current region preview supports source page 1 only")
        source = resolve_source_file(path, archive_root, suffixes={".cdr", ".cdt"})
        target = output.expanduser().resolve(strict=False)
        if target.suffix.casefold() != ".png":
            raise ValueError("region preview target must use .png")
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            raise FileExistsError(target)
        before = source_stat_guard(source)
        try:
            with self.bridge.session() as (application, active_document):
                active_path = str(getattr(active_document, "FullFileName", "") or "")
                if active_path and Path(active_path).resolve() == source:
                    raise CorelDrawBridgeError("source CDR is already active")
                opened = self._open_document(application, source)
                try:
                    shape_by_id, parent_by_id = self._shape_map(opened)
                    included = set(region.included_object_ids)
                    missing = included - set(shape_by_id)
                    if missing:
                        raise CorelDrawBridgeError(
                            "region references unavailable Corel objects: "
                            + ", ".join(sorted(missing))
                        )
                    top_level_ids = sorted(
                        object_id
                        for object_id in included
                        if parent_by_id[object_id] not in included
                    )
                    if not top_level_ids:
                        raise CorelDrawBridgeError("region contains no selectable objects")
                    try:
                        opened.ClearSelection()
                    except Exception:
                        pass
                    shape_range = application.CreateShapeRange()
                    for object_id in top_level_ids:
                        shape_range.Add(shape_by_id[object_id])
                    shape_range.CreateSelection()

                    export_width, export_height = bounded_export_size(
                        region.bounds.width,
                        region.bounds.height,
                        max_dimension=max_dimension,
                        max_pixels=max_pixels,
                    )
                    options = application.CreateStructExportOptions()
                    palette = application.CreateStructPaletteOptions()
                    options.ImageType = CDR_RGB_COLOR_IMAGE
                    options.Overwrite = False
                    options.ResolutionX = dpi
                    options.ResolutionY = dpi
                    options.MaintainAspect = True
                    options.SizeX = export_width
                    options.SizeY = export_height
                    export_filter = opened.ExportEx(
                        str(target), CDR_PNG, CDR_SELECTION, options, palette
                    )
                    export_filter.Finish()
                finally:
                    try:
                        opened.Close()
                    except Exception as exc:
                        raise CorelDrawBridgeError(
                            f"could not close source CDR without saving: {exc}"
                        ) from exc
        finally:
            assert_source_unchanged(source, before)
        if not target.is_file() or target.stat().st_size == 0:
            raise CorelDrawBridgeError("Corel region export produced no file")
        return target

    def _inspect_opened(
        self,
        application: Any,
        document: Any,
        source: Path,
        source_guard: tuple[int, int, int],
    ) -> CdrInspectionV1:
        page = document.ActivePage
        width = _float(page.SizeWidth)
        height = _float(page.SizeHeight)
        raw_shapes = list(_collection_items(getattr(page, "Shapes", page.ActiveLayer.Shapes)))
        objects: list[CdrObjectV1] = []
        used_object_ids: set[str] = set()
        font_families: set[str] = set()
        color_summary: list[dict[str, Any]] = []
        counts = {"text": 0, "image": 0, "group": 0, "vector": 0}

        def visit(shape: Any, *, parent_id: str | None = None) -> None:
            index = len(objects) + 1
            raw_name = str(getattr(shape, "Name", "") or f"object_{index}")
            base_object_id = _safe_name(raw_name, index)
            object_id = base_object_id
            suffix = 2
            while object_id in used_object_ids:
                object_id = f"{base_object_id}_{suffix}"
                suffix += 1
            used_object_ids.add(object_id)
            children = list(_collection_items(getattr(shape, "Shapes", [])))
            text, font, font_size, alignment = _shape_text(shape)
            kind = _shape_kind(shape, text, len(children))
            if kind in counts:
                counts[kind] += 1
            elif kind in {"rectangle", "ellipse"}:
                counts["vector"] += 1
            left = _float(getattr(shape, "LeftX", getattr(shape, "PositionX", 0)))
            bottom = _float(getattr(shape, "BottomY", getattr(shape, "PositionY", 0)))
            shape_width = max(1e-9, _float(getattr(shape, "SizeWidth", 0)))
            shape_height = max(1e-9, _float(getattr(shape, "SizeHeight", 0)))
            bbox, raw_bbox, bbox_clipped = _bounded_bbox(
                left=left,
                bottom=bottom,
                shape_width=shape_width,
                shape_height=shape_height,
                page_width=width,
                page_height=height,
            )
            fill = _shape_color(shape)
            if fill and fill not in color_summary:
                color_summary.append(fill)
            if font:
                font_families.add(font)
            objects.append(
                CdrObjectV1(
                    object_id=object_id,
                    corel_name=raw_name,
                    object_type=kind,
                    bbox=bbox,
                    bbox_norm={
                        "x": bbox["x"] / width,
                        "y": bbox["y"] / height,
                        "width": bbox["width"] / width,
                        "height": bbox["height"] / height,
                    },
                    rotation=_float(getattr(shape, "RotationAngle", 0)),
                    z_index=index,
                    layer=str(getattr(getattr(shape, "Layer", None), "Name", "default")),
                    parent_id=parent_id,
                    text=text,
                    font_family=font,
                    font_size=font_size,
                    alignment=alignment,
                    fill=fill,
                    metadata={
                        "corel_type": int(getattr(shape, "Type", 0) or 0),
                        "source_page": 1,
                        "source_layer": str(
                            getattr(getattr(shape, "Layer", None), "Name", "default")
                        ),
                        "visible": _bool(_attribute(shape, "Visible", True), True),
                        "printable": _bool(
                            _attribute(
                                _attribute(shape, "Layer", None),
                                "Printable",
                                None,
                            ),
                            None,
                        ),
                        "locked": _bool(_attribute(shape, "Locked", False), False),
                        "source_raw_bbox": raw_bbox,
                        "bbox_clipped_to_page": bbox_clipped,
                    },
                )
            )
            for child in children:
                visit(child, parent_id=object_id)

        for shape in raw_shapes:
            visit(shape)
        layers = list(_collection_items(getattr(page, "Layers", [])))
        pages = list(_collection_items(getattr(document, "Pages", [])))
        inspection = CdrInspectionV1(
            source_path=str(source),
            source_size_bytes=source_guard[0],
            source_mtime_ns=source_guard[1],
            corel_version=str(getattr(application, "Version", "unknown")),
            document_version=str(getattr(document, "Version", "")) or None,
            page_count=max(1, len(pages)),
            page_width=width,
            page_height=height,
            unit=COREL_UNITS.get(int(getattr(document, "Unit", -1)), "unknown"),
            corel_unit_code=int(getattr(document, "Unit", -1)),
            layer_count=len(layers),
            object_count=len(objects),
            text_object_count=counts["text"],
            bitmap_count=counts["image"],
            vector_count=counts["vector"],
            group_count=counts["group"],
            font_families=sorted(font_families),
            color_summary=color_summary,
            objects=objects,
            source_save_called=False,
        )
        return inspection
