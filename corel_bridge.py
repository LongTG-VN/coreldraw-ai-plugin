"""CorelDRAW COM automation bridge for basic CMYK vector operations."""

from __future__ import annotations

from contextlib import contextmanager
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
    """Small, thread-safe wrapper around the CorelDRAW COM application.

    FastAPI executes normal ``def`` endpoints in worker threads. COM requires a
    thread to initialize its apartment before use, so each operation opens a
    short-lived session and serializes access with a re-entrant lock.
    """

    def __init__(self, dispatcher: Optional[DispatchCallable] = None) -> None:
        self._dispatcher = dispatcher or (
            win32_client.Dispatch if win32_client is not None else None
        )
        self._lock = RLock()
        self.last_error: Optional[str] = None

    @property
    def is_available(self) -> bool:
        """Return whether a COM dispatcher is available in this environment."""

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

                app = self._dispatcher("CorelDRAW.Application")
                app.Visible = True
                doc = (
                    app.CreateDocument()
                    if int(app.Documents.Count) == 0
                    else app.ActiveDocument
                )
                self.last_error = None
                yield app, doc
            except CorelDrawBridgeError:
                raise
            except Exception as exc:  # COM exposes several runtime exception types.
                self.last_error = str(exc)
                raise CorelDrawBridgeError(
                    f"Không thể thực thi lệnh CorelDRAW: {exc}"
                ) from exc
            finally:
                if com_initialized and pythoncom is not None:
                    pythoncom.CoUninitialize()

    def connect(self) -> bool:
        """Verify that CorelDRAW can be reached and a document is available."""

        try:
            with self.session():
                return True
        except CorelDrawBridgeError:
            return False

    def connection_info(self) -> dict[str, Any]:
        """Return a small diagnostic snapshot of the CorelDRAW connection."""

        try:
            with self.session() as (app, doc):
                return {
                    "connected": True,
                    "application_version": str(getattr(app, "Version", "unknown")),
                    "document_name": str(getattr(doc, "Name", "Untitled")),
                }
        except CorelDrawBridgeError as exc:
            return {"connected": False, "error": str(exc)}

    @staticmethod
    def _generated_name(prefix: str) -> str:
        return f"ai_{prefix}_{uuid4().hex[:8]}"

    @staticmethod
    def _assign_shape_name(shape: Any, requested_name: Optional[str], prefix: str) -> str:
        target_name = requested_name or CorelDrawBridge._generated_name(prefix)
        try:
            shape.Name = target_name
            return str(shape.Name)
        except Exception:
            return str(getattr(shape, "Name", target_name))

    @staticmethod
    def _find_shape(layer: Any, shape_name: str) -> Any:
        """Find a shape by name, supporting COM collections across versions."""

        try:
            shape = layer.Shapes.Item(shape_name)
            if shape is not None:
                return shape
        except Exception:
            pass

        count = int(getattr(layer.Shapes, "Count", 0))
        for index in range(1, count + 1):
            shape = layer.Shapes.Item(index)
            if str(getattr(shape, "Name", "")) == shape_name:
                return shape
        raise CorelDrawBridgeError(f"Không tìm thấy shape '{shape_name}'.")

    @staticmethod
    def _create_cmyk_color(app: Any, c: int, m: int, y: int, k: int) -> Any:
        return app.CreateCMYKColor(c, m, y, k)

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
    info = corel_bridge.connection_info()
    print(info)
