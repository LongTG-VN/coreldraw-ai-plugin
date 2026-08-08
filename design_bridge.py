"""Agent-oriented CorelDRAW design operations.

This module exposes higher-level document inspection and mutation primitives for
AI controllers such as Antigravity. It deliberately reuses the serialized
CorelDrawBridge session so Python remains the only owner of COM state.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from corel_bridge import CorelDrawBridge, CorelDrawBridgeError, corel_bridge


SUPPORTED_IMPORT_SUFFIXES = {
    ".svg",
    ".eps",
    ".pdf",
    ".ai",
    ".cmx",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".bmp",
}


class DesignBridge:
    """Higher-level inspection and editing primitives for autonomous agents."""

    def __init__(self, bridge: CorelDrawBridge = corel_bridge) -> None:
        self.bridge = bridge

    @staticmethod
    def _float(value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _shape_text(shape: Any) -> str | None:
        try:
            story = shape.Text.Story
            value = getattr(story, "Text", None)
            if value is None:
                value = str(story)
            return str(value)
        except Exception:
            return None

    @staticmethod
    def _shape_type(shape: Any) -> int | str | None:
        value = getattr(shape, "Type", None)
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return str(value)

    def _shape_snapshot(self, shape: Any) -> dict[str, Any]:
        nested = getattr(shape, "Shapes", None)
        child_count = 0
        if nested is not None:
            try:
                child_count = int(getattr(nested, "Count", 0))
            except Exception:
                child_count = 0

        result: dict[str, Any] = {
            "name": str(getattr(shape, "Name", "")),
            "type": self._shape_type(shape),
            "x": self._float(getattr(shape, "LeftX", getattr(shape, "PositionX", 0))),
            "y": self._float(getattr(shape, "BottomY", getattr(shape, "PositionY", 0))),
            "width": self._float(getattr(shape, "SizeWidth", 0)),
            "height": self._float(getattr(shape, "SizeHeight", 0)),
            "rotation": self._float(getattr(shape, "RotationAngle", 0)),
            "child_count": child_count,
        }
        text = self._shape_text(shape)
        if text is not None:
            result["text"] = text
            try:
                result["font_size"] = self._float(shape.Text.Story.Size)
                result["font_name"] = str(shape.Text.Story.Font)
            except Exception:
                pass
        try:
            result["layer"] = str(shape.Layer.Name)
        except Exception:
            pass
        return result

    def snapshot(self) -> dict[str, Any]:
        """Return page metadata and a recursive list of document objects."""

        with self.bridge.session() as (app, doc):
            page = doc.ActivePage
            shapes = getattr(page, "Shapes", None)
            if shapes is None:
                shapes = page.ActiveLayer.Shapes
            items = [
                self._shape_snapshot(shape)
                for shape in self.bridge._iter_shapes_recursive(shapes)
            ]
            return {
                "application_version": str(getattr(app, "Version", "unknown")),
                "document_name": str(
                    getattr(doc, "Name", getattr(doc, "FileName", "Untitled"))
                ),
                "unit": int(getattr(doc, "Unit", 4) or 4),
                "page": {
                    "name": str(getattr(page, "Name", "Page 1")),
                    "width": self._float(getattr(page, "SizeWidth", 0)),
                    "height": self._float(getattr(page, "SizeHeight", 0)),
                },
                "object_count": len(items),
                "objects": items,
            }

    def transform_shape(
        self,
        shape_name: str,
        *,
        x: float | None = None,
        y: float | None = None,
        width: float | None = None,
        height: float | None = None,
        rotation: float | None = None,
    ) -> dict[str, Any]:
        """Move, resize, or rotate an existing object in document units."""

        if width is not None and width <= 0:
            raise CorelDrawBridgeError("width phải lớn hơn 0.")
        if height is not None and height <= 0:
            raise CorelDrawBridgeError("height phải lớn hơn 0.")

        with self.bridge.session() as (_app, doc):
            shape = self.bridge._find_shape_in_document(doc, shape_name)
            current_x = self._float(
                getattr(shape, "LeftX", getattr(shape, "PositionX", 0))
            )
            current_y = self._float(
                getattr(shape, "BottomY", getattr(shape, "PositionY", 0))
            )
            current_width = self._float(getattr(shape, "SizeWidth", 0))
            current_height = self._float(getattr(shape, "SizeHeight", 0))

            if width is not None or height is not None:
                target_width = width if width is not None else current_width
                target_height = height if height is not None else current_height
                try:
                    shape.SetSize(target_width, target_height)
                except Exception:
                    shape.SizeWidth = target_width
                    shape.SizeHeight = target_height

            if x is not None or y is not None:
                target_x = x if x is not None else current_x
                target_y = y if y is not None else current_y
                try:
                    shape.SetPosition(target_x, target_y)
                except Exception:
                    shape.PositionX = target_x
                    shape.PositionY = target_y

            if rotation is not None:
                try:
                    shape.RotationAngle = rotation
                except Exception as exc:
                    raise CorelDrawBridgeError(
                        f"Không thể xoay shape '{shape_name}': {exc}"
                    ) from exc

            return self._shape_snapshot(shape)

    def duplicate_shape(
        self,
        shape_name: str,
        *,
        offset_x: float = 0,
        offset_y: float = 0,
        new_name: str | None = None,
    ) -> dict[str, Any]:
        """Duplicate one object and optionally offset/name the copy."""

        with self.bridge.session() as (_app, doc):
            shape = self.bridge._find_shape_in_document(doc, shape_name)
            try:
                duplicate = shape.Duplicate(offset_x, offset_y)
            except Exception as exc:
                raise CorelDrawBridgeError(
                    f"Không thể duplicate shape '{shape_name}': {exc}"
                ) from exc
            self.bridge._assign_shape_name(duplicate, new_name, "duplicate")
            return self._shape_snapshot(duplicate)

    def set_fill_cmyk(
        self,
        shape_name: str,
        c: int,
        m: int,
        y: int,
        k: int,
    ) -> dict[str, Any]:
        """Apply a uniform CMYK fill to an object."""

        with self.bridge.session() as (app, doc):
            shape = self.bridge._find_shape_in_document(doc, shape_name)
            try:
                shape.Fill.ApplyUniformFill(
                    self.bridge._create_cmyk_color(app, c, m, y, k)
                )
            except Exception as exc:
                raise CorelDrawBridgeError(
                    f"Không thể tô màu shape '{shape_name}': {exc}"
                ) from exc
            return self._shape_snapshot(shape)

    def import_asset(
        self,
        file_path: str,
        *,
        name: str | None = None,
        x: float | None = None,
        y: float | None = None,
        width: float | None = None,
        height: float | None = None,
    ) -> dict[str, Any]:
        """Import SVG/vector/bitmap artwork through CorelDRAW auto-sense import."""

        source = Path(file_path).expanduser().resolve()
        if not source.is_file():
            raise CorelDrawBridgeError(f"Asset không tồn tại: {source}")
        if source.suffix.lower() not in SUPPORTED_IMPORT_SUFFIXES:
            raise CorelDrawBridgeError(
                "Định dạng import chưa được allow-list: " + source.suffix.lower()
            )
        if width is not None and width <= 0:
            raise CorelDrawBridgeError("width phải lớn hơn 0.")
        if height is not None and height <= 0:
            raise CorelDrawBridgeError("height phải lớn hơn 0.")

        with self.bridge.session() as (_app, doc):
            layer = doc.ActivePage.ActiveLayer
            try:
                import_result = layer.Import(str(source))
                imported = self.bridge._imported_shape(import_result, doc, layer)
            except Exception as exc:
                if isinstance(exc, CorelDrawBridgeError):
                    raise
                raise CorelDrawBridgeError(
                    f"Không thể import asset '{source}': {exc}"
                ) from exc

            self.bridge._assign_shape_name(imported, name, "asset")
            current = self._shape_snapshot(imported)
            if width is not None or height is not None:
                target_width = width if width is not None else current["width"]
                target_height = height if height is not None else current["height"]
                try:
                    imported.SetSize(target_width, target_height)
                except Exception:
                    imported.SizeWidth = target_width
                    imported.SizeHeight = target_height
            if x is not None or y is not None:
                target_x = x if x is not None else current["x"]
                target_y = y if y is not None else current["y"]
                try:
                    imported.SetPosition(target_x, target_y)
                except Exception:
                    imported.PositionX = target_x
                    imported.PositionY = target_y
            result = self._shape_snapshot(imported)
            result["source_path"] = str(source)
            return result

    def delete_shape(self, shape_name: str) -> dict[str, object]:
        with self.bridge.session() as (_app, doc):
            shape = self.bridge._find_shape_in_document(doc, shape_name)
            try:
                shape.Delete()
            except Exception as exc:
                raise CorelDrawBridgeError(
                    f"Không thể xóa shape '{shape_name}': {exc}"
                ) from exc
        return {"shape_name": shape_name, "deleted": True}

    def undo(self, steps: int = 1) -> dict[str, int]:
        """Undo one or more recent CorelDRAW operations."""

        if steps < 1 or steps > 50:
            raise CorelDrawBridgeError("steps phải nằm trong khoảng 1..50.")
        with self.bridge.session() as (_app, doc):
            completed = 0
            for _ in range(steps):
                try:
                    doc.Undo()
                    completed += 1
                except Exception as exc:
                    if completed == 0:
                        raise CorelDrawBridgeError(f"Không thể undo: {exc}") from exc
                    break
        return {"requested_steps": steps, "completed_steps": completed}

    def check_design(
        self,
        *,
        min_font_size: float = 6.0,
        require_named_objects: bool = False,
    ) -> dict[str, Any]:
        """Run deterministic agent guardrails before a design is accepted."""

        snapshot = self.snapshot()
        page_width = float(snapshot["page"]["width"])
        page_height = float(snapshot["page"]["height"])
        issues: list[dict[str, Any]] = []

        for item in snapshot["objects"]:
            name = item.get("name") or "<unnamed>"
            x = float(item.get("x", 0))
            y = float(item.get("y", 0))
            width = float(item.get("width", 0))
            height = float(item.get("height", 0))

            if require_named_objects and not item.get("name"):
                issues.append(
                    {"severity": "warning", "code": "unnamed_object", "object": name}
                )
            if width <= 0 or height <= 0:
                issues.append(
                    {"severity": "error", "code": "invalid_size", "object": name}
                )
            if page_width > 0 and page_height > 0:
                if x < 0 or y < 0 or x + width > page_width or y + height > page_height:
                    issues.append(
                        {"severity": "warning", "code": "outside_page", "object": name}
                    )
            font_size = item.get("font_size")
            if font_size is not None and float(font_size) < min_font_size:
                issues.append(
                    {
                        "severity": "warning",
                        "code": "small_text",
                        "object": name,
                        "font_size": float(font_size),
                        "minimum": min_font_size,
                    }
                )

        errors = sum(1 for issue in issues if issue["severity"] == "error")
        warnings = len(issues) - errors
        return {
            "status": "pass" if errors == 0 else "fail",
            "errors": errors,
            "warnings": warnings,
            "issues": issues,
            "snapshot": snapshot,
        }


design_bridge = DesignBridge()
