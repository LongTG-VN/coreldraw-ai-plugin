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

    @staticmethod
    def _set_position(shape: Any, x: float, y: float) -> None:
        try:
            shape.SetPosition(x, y)
        except Exception:
            try:
                shape.LeftX = x
                shape.BottomY = y
            except Exception:
                shape.PositionX = x
                shape.PositionY = y

    @staticmethod
    def _set_size(shape: Any, width: float, height: float) -> None:
        try:
            shape.SetSize(width, height)
        except Exception:
            shape.SizeWidth = width
            shape.SizeHeight = height

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

    def _transform_shape_object(
        self,
        shape: Any,
        *,
        x: float | None = None,
        y: float | None = None,
        width: float | None = None,
        height: float | None = None,
        rotation: float | None = None,
    ) -> dict[str, Any]:
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
            self._set_size(shape, target_width, target_height)

        if x is not None or y is not None:
            target_x = x if x is not None else current_x
            target_y = y if y is not None else current_y
            self._set_position(shape, target_x, target_y)

        if rotation is not None:
            try:
                shape.RotationAngle = rotation
            except Exception as exc:
                raise CorelDrawBridgeError(
                    f"Không thể xoay shape '{getattr(shape, 'Name', '')}': {exc}"
                ) from exc

        return self._shape_snapshot(shape)

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
            return self._transform_shape_object(
                shape,
                x=x,
                y=y,
                width=width,
                height=height,
                rotation=rotation,
            )

    def batch_transform(self, operations: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Apply multiple transforms while holding one serialized COM session."""

        if not operations:
            raise CorelDrawBridgeError("operations không được rỗng.")
        if len(operations) > 500:
            raise CorelDrawBridgeError("Tối đa 500 transforms cho một request.")

        results: list[dict[str, Any]] = []
        with self.bridge.session() as (_app, doc):
            for operation in operations:
                name = str(operation.get("shape_name") or "").strip()
                if not name:
                    raise CorelDrawBridgeError("Mỗi operation phải có shape_name.")
                width = operation.get("width")
                height = operation.get("height")
                if width is not None and float(width) <= 0:
                    raise CorelDrawBridgeError("width phải lớn hơn 0.")
                if height is not None and float(height) <= 0:
                    raise CorelDrawBridgeError("height phải lớn hơn 0.")
                shape = self.bridge._find_shape_in_document(doc, name)
                results.append(
                    self._transform_shape_object(
                        shape,
                        x=operation.get("x"),
                        y=operation.get("y"),
                        width=width,
                        height=height,
                        rotation=operation.get("rotation"),
                    )
                )
        return results

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

    def set_typography(
        self,
        shape_name: str,
        *,
        text: str | None = None,
        font_name: str | None = None,
        font_size: float | None = None,
    ) -> dict[str, Any]:
        """Update editable text content and basic typography properties."""

        if font_size is not None and font_size <= 0:
            raise CorelDrawBridgeError("font_size phải lớn hơn 0.")
        with self.bridge.session() as (_app, doc):
            shape = self.bridge._find_shape_in_document(doc, shape_name)
            try:
                story = shape.Text.Story
            except Exception as exc:
                raise CorelDrawBridgeError(
                    f"Shape '{shape_name}' không phải text có thể chỉnh sửa."
                ) from exc

            try:
                if text is not None:
                    try:
                        story.Text = text
                    except Exception:
                        shape.Text.Story = text
                if font_name is not None:
                    story.Font = font_name
                if font_size is not None:
                    story.Size = font_size
            except Exception as exc:
                raise CorelDrawBridgeError(
                    f"Không thể cập nhật typography cho '{shape_name}': {exc}"
                ) from exc
            return self._shape_snapshot(shape)

    def order_shape(
        self,
        shape_name: str,
        mode: str,
        *,
        relative_to: str | None = None,
    ) -> dict[str, Any]:
        """Change stacking order using CorelDRAW's native ordering methods."""

        normalized = mode.strip().lower()
        allowed = {"front", "back", "front_of", "back_of"}
        if normalized not in allowed:
            raise CorelDrawBridgeError(
                "mode phải là front, back, front_of hoặc back_of."
            )
        if normalized in {"front_of", "back_of"} and not relative_to:
            raise CorelDrawBridgeError("relative_to là bắt buộc cho *_of.")

        with self.bridge.session() as (_app, doc):
            shape = self.bridge._find_shape_in_document(doc, shape_name)
            try:
                if normalized == "front":
                    shape.OrderToFront()
                elif normalized == "back":
                    shape.OrderToBack()
                else:
                    reference = self.bridge._find_shape_in_document(doc, str(relative_to))
                    if normalized == "front_of":
                        shape.OrderFrontOf(reference)
                    else:
                        shape.OrderBackOf(reference)
            except Exception as exc:
                raise CorelDrawBridgeError(
                    f"Không thể đổi z-order cho '{shape_name}': {exc}"
                ) from exc
            result = self._shape_snapshot(shape)
            result["order_mode"] = normalized
            if relative_to:
                result["relative_to"] = relative_to
            return result

    @staticmethod
    def _selection_bounds(items: list[dict[str, Any]]) -> dict[str, float]:
        left = min(float(item["x"]) for item in items)
        bottom = min(float(item["y"]) for item in items)
        right = max(float(item["x"]) + float(item["width"]) for item in items)
        top = max(float(item["y"]) + float(item["height"]) for item in items)
        return {
            "left": left,
            "bottom": bottom,
            "right": right,
            "top": top,
            "center_x": (left + right) / 2,
            "center_y": (bottom + top) / 2,
        }

    def align_shapes(
        self,
        shape_names: list[str],
        *,
        horizontal: str | None = None,
        vertical: str | None = None,
        relative_to: str = "selection",
    ) -> list[dict[str, Any]]:
        """Align objects deterministically to selection bounds or the active page."""

        names = list(dict.fromkeys(shape_names))
        if len(names) < 2:
            raise CorelDrawBridgeError("Cần ít nhất 2 shape để align.")
        if horizontal is None and vertical is None:
            raise CorelDrawBridgeError("Phải truyền horizontal hoặc vertical.")

        h = horizontal.lower() if horizontal else None
        v = vertical.lower() if vertical else None
        if h not in {None, "left", "center", "right"}:
            raise CorelDrawBridgeError("horizontal phải là left, center hoặc right.")
        if v not in {None, "bottom", "center", "top"}:
            raise CorelDrawBridgeError("vertical phải là bottom, center hoặc top.")
        target = relative_to.strip().lower()
        if target not in {"selection", "page"}:
            raise CorelDrawBridgeError("relative_to phải là selection hoặc page.")

        with self.bridge.session() as (_app, doc):
            shapes = [self.bridge._find_shape_in_document(doc, name) for name in names]
            items = [self._shape_snapshot(shape) for shape in shapes]
            if target == "page":
                page = doc.ActivePage
                width = self._float(getattr(page, "SizeWidth", 0))
                height = self._float(getattr(page, "SizeHeight", 0))
                bounds = {
                    "left": 0.0,
                    "bottom": 0.0,
                    "right": width,
                    "top": height,
                    "center_x": width / 2,
                    "center_y": height / 2,
                }
            else:
                bounds = self._selection_bounds(items)

            results: list[dict[str, Any]] = []
            for shape, item in zip(shapes, items):
                x = float(item["x"])
                y = float(item["y"])
                width = float(item["width"])
                height = float(item["height"])

                if h == "left":
                    x = bounds["left"]
                elif h == "center":
                    x = bounds["center_x"] - width / 2
                elif h == "right":
                    x = bounds["right"] - width

                if v == "bottom":
                    y = bounds["bottom"]
                elif v == "center":
                    y = bounds["center_y"] - height / 2
                elif v == "top":
                    y = bounds["top"] - height

                self._set_position(shape, x, y)
                results.append(self._shape_snapshot(shape))
            return results

    def distribute_shapes(
        self,
        shape_names: list[str],
        *,
        axis: str,
        mode: str = "gaps",
    ) -> list[dict[str, Any]]:
        """Distribute three or more objects evenly by gaps or centers."""

        names = list(dict.fromkeys(shape_names))
        if len(names) < 3:
            raise CorelDrawBridgeError("Cần ít nhất 3 shape để distribute.")
        axis_name = axis.strip().lower()
        mode_name = mode.strip().lower()
        if axis_name not in {"horizontal", "vertical"}:
            raise CorelDrawBridgeError("axis phải là horizontal hoặc vertical.")
        if mode_name not in {"gaps", "centers"}:
            raise CorelDrawBridgeError("mode phải là gaps hoặc centers.")

        with self.bridge.session() as (_app, doc):
            shapes = [self.bridge._find_shape_in_document(doc, name) for name in names]
            records = [(shape, self._shape_snapshot(shape)) for shape in shapes]
            key = "x" if axis_name == "horizontal" else "y"
            size_key = "width" if axis_name == "horizontal" else "height"
            records.sort(key=lambda pair: float(pair[1][key]))

            first = records[0][1]
            last = records[-1][1]
            if mode_name == "centers":
                first_center = float(first[key]) + float(first[size_key]) / 2
                last_center = float(last[key]) + float(last[size_key]) / 2
                step = (last_center - first_center) / (len(records) - 1)
                for index, (shape, item) in enumerate(records[1:-1], start=1):
                    target_center = first_center + step * index
                    coordinate = target_center - float(item[size_key]) / 2
                    if axis_name == "horizontal":
                        self._set_position(shape, coordinate, float(item["y"]))
                    else:
                        self._set_position(shape, float(item["x"]), coordinate)
            else:
                start = float(first[key])
                end = float(last[key]) + float(last[size_key])
                total_size = sum(float(item[size_key]) for _, item in records)
                gap = (end - start - total_size) / (len(records) - 1)
                cursor = start + float(first[size_key]) + gap
                for shape, item in records[1:-1]:
                    if axis_name == "horizontal":
                        self._set_position(shape, cursor, float(item["y"]))
                    else:
                        self._set_position(shape, float(item["x"]), cursor)
                    cursor += float(item[size_key]) + gap

            return [self._shape_snapshot(shape) for shape, _ in records]

    def set_page_size(self, width: float, height: float) -> dict[str, float]:
        """Resize the active page in the current document unit."""

        if width <= 0 or height <= 0:
            raise CorelDrawBridgeError("Page width/height phải lớn hơn 0.")
        with self.bridge.session() as (_app, doc):
            page = doc.ActivePage
            try:
                page.SetSize(width, height)
            except Exception:
                try:
                    page.SizeWidth = width
                    page.SizeHeight = height
                except Exception as exc:
                    raise CorelDrawBridgeError(
                        f"Không thể resize active page: {exc}"
                    ) from exc
            return {
                "width": self._float(getattr(page, "SizeWidth", width), width),
                "height": self._float(getattr(page, "SizeHeight", height), height),
            }

    def fit_shape_to_frame(
        self,
        shape_name: str,
        frame_shape_name: str,
        *,
        mode: str = "cover",
        powerclip: bool = False,
        lock_contents: bool = True,
    ) -> dict[str, Any]:
        """Aspect-fit/cover an object to a named frame and optionally PowerClip it."""

        fit_mode = mode.strip().lower()
        if fit_mode not in {"contain", "cover"}:
            raise CorelDrawBridgeError("mode phải là contain hoặc cover.")

        with self.bridge.session() as (_app, doc):
            shape = self.bridge._find_shape_in_document(doc, shape_name)
            frame = self.bridge._find_shape_in_document(doc, frame_shape_name)
            item = self._shape_snapshot(shape)
            frame_item = self._shape_snapshot(frame)
            source_width = float(item["width"])
            source_height = float(item["height"])
            frame_width = float(frame_item["width"])
            frame_height = float(frame_item["height"])
            if min(source_width, source_height, frame_width, frame_height) <= 0:
                raise CorelDrawBridgeError("Shape/frame phải có kích thước dương.")

            scale_x = frame_width / source_width
            scale_y = frame_height / source_height
            scale = min(scale_x, scale_y) if fit_mode == "contain" else max(scale_x, scale_y)
            new_width = source_width * scale
            new_height = source_height * scale
            new_x = float(frame_item["x"]) + (frame_width - new_width) / 2
            new_y = float(frame_item["y"]) + (frame_height - new_height) / 2
            self._set_size(shape, new_width, new_height)
            self._set_position(shape, new_x, new_y)

            if powerclip:
                try:
                    shape.AddToPowerClip(frame)
                    try:
                        frame.PowerClip.ContentsLocked = lock_contents
                    except Exception:
                        pass
                except Exception as exc:
                    raise CorelDrawBridgeError(
                        f"Không thể PowerClip '{shape_name}' vào '{frame_shape_name}': {exc}"
                    ) from exc

            return {
                "mode": fit_mode,
                "powerclip": powerclip,
                "frame": self._shape_snapshot(frame),
                "object": self._shape_snapshot(shape),
            }

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
                self._set_size(imported, target_width, target_height)
            if x is not None or y is not None:
                target_x = x if x is not None else current["x"]
                target_y = y if y is not None else current["y"]
                self._set_position(imported, target_x, target_y)
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
