"""CorelDRAW COM automation bridge for CMYK vector and template operations."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from threading import RLock
from typing import Any, Callable, Iterator, Optional
from uuid import uuid4

try:  # Only available on Windows with pywin32 installed.
    import pythoncom  # type: ignore
    import win32com.client as win32_client  # type: ignore
except ImportError:  # pragma: no cover - expected on Linux CI.
    pythoncom = None
    win32_client = None


class CorelDrawBridgeError(RuntimeError):
    """Raised when CorelDRAW cannot execute an automation command."""


DispatchCallable = Callable[[str], Any]


class CorelDrawBridge:
    """Thread-safe wrapper around the CorelDRAW COM application.

    FastAPI executes sync endpoints in worker threads. Each operation therefore
    initializes its COM apartment and all calls are serialized to avoid two
    requests editing the active CorelDRAW document at the same time.
    """

    def __init__(self, dispatcher: Optional[DispatchCallable] = None) -> None:
        self._dispatcher = dispatcher or (
            win32_client.Dispatch if win32_client is not None else None
        )
        self._lock = RLock()
        self.last_error: Optional[str] = None

    @property
    def is_available(self) -> bool:
        return self._dispatcher is not None

    @contextmanager
    def session(self) -> Iterator[tuple[Any, Any]]:
        """Yield the CorelDRAW application and an active document."""

        if self._dispatcher is None:
            raise CorelDrawBridgeError(
                "pywin32 chưa được cài đặt hoặc server không chạy trên Windows."
            )

        with self._lock:
            com_initialized = False
            try:
                if pythoncom is not None:
                    pythoncom.CoInitialize()
                    com_initialized = True

                try:
                    app = win32_client.GetActiveObject("CorelDRAW.Application")
                except Exception:
                    app = self._dispatcher("CorelDRAW.Application")

                app.Visible = True
                doc = getattr(app, "ActiveDocument", None)
                if doc is None or int(getattr(app.Documents, "Count", 0)) == 0:
                    doc = app.CreateDocument()

                try:
                    doc.Unit = 3  # Corel cdrMillimeter enum value (3).
                except Exception:
                    pass

                self.last_error = None
                yield app, doc
                try:
                    if hasattr(app, "ActiveWindow") and app.ActiveWindow is not None:
                        app.ActiveWindow.ActiveView.ToFitPage()
                        app.ActiveWindow.Refresh()
                except Exception:
                    pass
            except CorelDrawBridgeError:
                raise
            except Exception as exc:
                self.last_error = str(exc)
                raise CorelDrawBridgeError(
                    f"Không thể thực thi lệnh CorelDRAW: {exc}"
                ) from exc
            finally:
                if com_initialized and pythoncom is not None:
                    pythoncom.CoUninitialize()

    def connect(self) -> bool:
        try:
            with self.session():
                return True
        except CorelDrawBridgeError:
            return False

    def connection_info(self) -> dict[str, Any]:
        try:
            with self.session() as (app, doc):
                return {
                    "connected": True,
                    "application_version": str(getattr(app, "Version", "unknown")),
                    "document_name": str(
                        getattr(doc, "Name", getattr(doc, "FileName", "Untitled"))
                    ),
                }
        except CorelDrawBridgeError as exc:
            return {"connected": False, "error": str(exc)}

    @staticmethod
    def _generated_name(prefix: str) -> str:
        return f"ai_{prefix}_{uuid4().hex[:8]}"

    @staticmethod
    def _assign_shape_name(
        shape: Any, requested_name: Optional[str], prefix: str
    ) -> str:
        target_name = requested_name or CorelDrawBridge._generated_name(prefix)
        try:
            shape.Name = target_name
            return str(shape.Name)
        except Exception:
            return str(getattr(shape, "Name", target_name))

    @staticmethod
    def _collection_items(collection: Any) -> Iterator[Any]:
        """Iterate COM collections that may not support normal Python iteration."""

        try:
            for item in collection:
                yield item
            return
        except Exception:
            pass

        count = int(getattr(collection, "Count", 0))
        for index in range(1, count + 1):
            try:
                yield collection.Item(index)
            except Exception:
                try:
                    yield collection(index)
                except Exception:
                    continue

    @classmethod
    def _iter_shapes_recursive(cls, shapes: Any) -> Iterator[Any]:
        for shape in cls._collection_items(shapes):
            yield shape
            nested = getattr(shape, "Shapes", None)
            if nested is not None:
                yield from cls._iter_shapes_recursive(nested)

    @classmethod
    def _find_shape(cls, container: Any, shape_name: str) -> Any:
        """Find a named shape in a layer, page, document, or shape collection."""

        shapes = getattr(container, "Shapes", container)
        try:
            shape = shapes.Item(shape_name)
            if shape is not None:
                return shape
        except Exception:
            pass
        try:
            shape = shapes(shape_name)
            if shape is not None:
                return shape
        except Exception:
            pass

        for shape in cls._iter_shapes_recursive(shapes):
            if str(getattr(shape, "Name", "")) == shape_name:
                return shape
        raise CorelDrawBridgeError(f"Không tìm thấy shape '{shape_name}'.")

    @classmethod
    def _find_shape_in_document(cls, doc: Any, shape_name: str) -> Any:
        page = doc.ActivePage
        try:
            return cls._find_shape(page, shape_name)
        except CorelDrawBridgeError:
            pass

        for layer in cls._collection_items(getattr(page, "Layers", [])):
            try:
                return cls._find_shape(layer, shape_name)
            except CorelDrawBridgeError:
                continue
        raise CorelDrawBridgeError(f"Không tìm thấy shape '{shape_name}'.")

    @staticmethod
    def _create_cmyk_color(app: Any, c: int, m: int, y: int, k: int) -> Any:
        return app.CreateCMYKColor(c, m, y, k)

    @staticmethod
    def _normalize_output_path(path: str, suffix: str) -> Path:
        target = Path(path).expanduser()
        if target.suffix.lower() != suffix.lower():
            target = target.with_suffix(suffix)
        if not target.is_absolute():
            target = Path.cwd() / target
        target.parent.mkdir(parents=True, exist_ok=True)
        return target.resolve()

    def open_document(self, path: str) -> str:
        """Open a .cdr template and make it the active CorelDRAW document."""

        source = Path(path).expanduser().resolve()
        if not source.is_file():
            raise CorelDrawBridgeError(f"Template CorelDRAW không tồn tại: {source}")
        with self.session() as (app, _doc):
            opened = app.OpenDocument(str(source))
            return str(
                getattr(opened, "FullFileName", None)
                or getattr(opened, "FileName", None)
                or source
            )

    def save_document(self, path: str) -> str:
        """Save the active document as an editable CorelDRAW .cdr file."""

        target = self._normalize_output_path(path, ".cdr")
        with self.session() as (app, doc):
            try:
                options = app.CreateStructSaveAsOptions()
                options.Overwrite = True
                doc.SaveAs(str(target), options)
            except Exception:
                try:
                    doc.SaveAs(str(target))
                except Exception as exc:
                    raise CorelDrawBridgeError(
                        f"Không thể lưu file CDR tại '{target}': {exc}"
                    ) from exc
        return str(target)

    def list_shape_names(self) -> list[str]:
        """Return all named shapes on the active page, including nested groups."""

        with self.session() as (_app, doc):
            page = doc.ActivePage
            shapes = getattr(page, "Shapes", None)
            if shapes is None:
                layer = page.ActiveLayer
                shapes = layer.Shapes
            return [
                str(shape.Name)
                for shape in self._iter_shapes_recursive(shapes)
                if str(getattr(shape, "Name", ""))
            ]

    def shape_exists(self, shape_name: str) -> bool:
        try:
            with self.session() as (_app, doc):
                self._find_shape_in_document(doc, shape_name)
                return True
        except CorelDrawBridgeError:
            return False

    def set_text_content(
        self,
        shape_name: str,
        text_content: str,
        *,
        max_length: int | None = None,
        min_font_size: float = 10.0,
        max_width: float | None = None,
    ) -> dict[str, Any]:
        """Replace a template text shape and optionally shrink it to a max width."""

        if max_length is not None and len(text_content) > max_length:
            raise CorelDrawBridgeError(
                f"Nội dung cho '{shape_name}' vượt quá {max_length} ký tự."
            )

        with self.session() as (_app, doc):
            shape = self._find_shape_in_document(doc, shape_name)
            try:
                story = shape.Text.Story
                current_size = float(getattr(story, "Size", 0) or 0)
                try:
                    story.Text = text_content
                except Exception:
                    shape.Text.Story = text_content
            except Exception as exc:
                raise CorelDrawBridgeError(
                    f"Shape '{shape_name}' không phải text có thể chỉnh sửa."
                ) from exc

            final_size = current_size
            shape_width = float(getattr(shape, "SizeWidth", 0) or 0)
            if max_width and shape_width > max_width and current_size > 0:
                ratio = max_width / shape_width
                final_size = max(min_font_size, current_size * ratio)
                try:
                    shape.Text.Story.Size = final_size
                except Exception:
                    pass

            return {
                "shape_name": str(getattr(shape, "Name", shape_name)),
                "text": text_content,
                "font_size": final_size,
                "width": float(getattr(shape, "SizeWidth", 0) or 0),
            }

    def get_shape_bounds(self, shape_name: str) -> dict[str, float]:
        """Read a shape's left/bottom position and size in the document unit."""

        with self.session() as (_app, doc):
            shape = self._find_shape_in_document(doc, shape_name)
            left = float(
                getattr(shape, "LeftX", getattr(shape, "PositionX", 0)) or 0
            )
            bottom = float(
                getattr(shape, "BottomY", getattr(shape, "PositionY", 0)) or 0
            )
            return {
                "x": left,
                "y": bottom,
                "width": float(getattr(shape, "SizeWidth", 0) or 0),
                "height": float(getattr(shape, "SizeHeight", 0) or 0),
            }

    @staticmethod
    def _imported_shape(import_result: Any, doc: Any, layer: Any) -> Any:
        if import_result is not None and hasattr(import_result, "SizeWidth"):
            return import_result
        try:
            selection = doc.ActiveSelectionRange
            if int(selection.Shapes.Count) > 0:
                return selection.Shapes.Item(1)
        except Exception:
            pass
        try:
            return layer.Shapes.Item(1)
        except Exception as exc:
            raise CorelDrawBridgeError("Không xác định được bitmap vừa import.") from exc

    def import_image_into_slot(
        self,
        image_path: str,
        slot_shape_name: str,
        *,
        imported_shape_name: str | None = None,
        delete_slot: bool = False,
    ) -> dict[str, Any]:
        """Import a bitmap and fit it to a named image-slot rectangle."""

        source = Path(image_path).expanduser().resolve()
        if not source.is_file():
            raise CorelDrawBridgeError(f"Ảnh không tồn tại: {source}")

        with self.session() as (_app, doc):
            slot = self._find_shape_in_document(doc, slot_shape_name)
            bounds = {
                "x": float(
                    getattr(slot, "LeftX", getattr(slot, "PositionX", 0)) or 0
                ),
                "y": float(
                    getattr(slot, "BottomY", getattr(slot, "PositionY", 0)) or 0
                ),
                "width": float(getattr(slot, "SizeWidth", 0) or 0),
                "height": float(getattr(slot, "SizeHeight", 0) or 0),
            }
            layer = doc.ActivePage.ActiveLayer
            imported = self._imported_shape(layer.Import(str(source)), doc, layer)

            try:
                imported.SetSize(bounds["width"], bounds["height"])
            except Exception:
                imported.SizeWidth = bounds["width"]
                imported.SizeHeight = bounds["height"]
            try:
                imported.SetPosition(bounds["x"], bounds["y"])
            except Exception:
                try:
                    imported.LeftX = bounds["x"]
                    imported.BottomY = bounds["y"]
                except Exception:
                    imported.PositionX = bounds["x"]
                    imported.PositionY = bounds["y"]

            assigned_name = self._assign_shape_name(
                imported, imported_shape_name, "image"
            )
            if delete_slot:
                try:
                    slot.Delete()
                except Exception:
                    pass
            return {
                "shape_name": assigned_name,
                "slot_shape_name": slot_shape_name,
                "image_path": str(source),
                **bounds,
            }

    def delete_shape(self, shape_name: str) -> None:
        with self.session() as (_app, doc):
            shape = self._find_shape_in_document(doc, shape_name)
            shape.Delete()

    def create_rectangle_cmyk(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        c: int,
        m: int,
        y_col: int,
        k: int,
        shape_name: Optional[str] = None,
    ) -> str:
        """Create a rectangle using left/top coordinates and positive dimensions."""

        with self.session() as (app, doc):
            layer = doc.ActivePage.ActiveLayer
            shape = layer.CreateRectangle(x, y, x + width, y - height)
            shape.Fill.ApplyUniformFill(
                self._create_cmyk_color(app, c, m, y_col, k)
            )
            return self._assign_shape_name(shape, shape_name, "rectangle")

    def create_ellipse_cmyk(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        c: int,
        m: int,
        y_col: int,
        k: int,
        shape_name: Optional[str] = None,
    ) -> str:
        """Create an ellipse using the corners of its bounding box."""

        with self.session() as (app, doc):
            layer = doc.ActivePage.ActiveLayer
            shape = layer.CreateEllipse(x, y, x + width, y - height)
            shape.Fill.ApplyUniformFill(
                self._create_cmyk_color(app, c, m, y_col, k)
            )
            return self._assign_shape_name(shape, shape_name, "ellipse")

    def create_artistic_text_cmyk(
        self,
        text_content: str,
        x: float,
        y: float,
        font_name: str = "Arial",
        font_size: float = 24.0,
        c: int = 0,
        m: int = 0,
        y_col: int = 0,
        k: int = 100,
        shape_name: Optional[str] = None,
    ) -> str:
        """Create artistic text and apply font, size, and CMYK fill."""

        with self.session() as (app, doc):
            layer = doc.ActivePage.ActiveLayer
            shape = layer.CreateArtisticText(x, y, text_content)
            shape.Text.Story.Font = font_name
            shape.Text.Story.Size = font_size
            shape.Fill.ApplyUniformFill(
                self._create_cmyk_color(app, c, m, y_col, k)
            )
            return self._assign_shape_name(shape, shape_name, "text")


corel_bridge = CorelDrawBridge()


if __name__ == "__main__":
    print(corel_bridge.connection_info())
