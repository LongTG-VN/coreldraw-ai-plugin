"""Safe local document lifecycle operations for the agent-facing Design API."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from corel_bridge import CorelDrawBridge, CorelDrawBridgeError, corel_bridge
from extended_bridge import ExtendedCorelDrawBridge, extended_bridge


ExportFormat = Literal["pdf", "png"]


def validate_local_path(
    file_path: str,
    *,
    extensions: set[str],
    must_exist: bool,
    overwrite: bool = False,
) -> Path:
    """Validate an explicit absolute local path without silently rewriting it."""

    raw = Path(file_path).expanduser()
    if not raw.is_absolute():
        raise CorelDrawBridgeError("Đường dẫn phải là đường dẫn tuyệt đối trên máy local.")
    if ".." in raw.parts:
        raise CorelDrawBridgeError("Đường dẫn không được chứa thành phần '..'.")
    if raw.suffix.casefold() not in {item.casefold() for item in extensions}:
        expected = ", ".join(sorted(extensions))
        raise CorelDrawBridgeError(f"Phần mở rộng không hợp lệ; yêu cầu: {expected}.")

    resolved = raw.resolve(strict=False)
    if must_exist:
        if not resolved.is_file():
            raise CorelDrawBridgeError(f"File không tồn tại: {resolved}")
    else:
        if not resolved.parent.is_dir():
            raise CorelDrawBridgeError(
                f"Thư mục đích chưa tồn tại: {resolved.parent}"
            )
        if resolved.exists() and not overwrite:
            raise CorelDrawBridgeError(
                f"File đích đã tồn tại và overwrite=false: {resolved}"
            )
        if resolved.exists() and not resolved.is_file():
            raise CorelDrawBridgeError(f"Đích không phải file: {resolved}")
    return resolved


def _document_file_name(document: Any) -> str | None:
    for attribute in ("FullFileName", "FileName"):
        value = getattr(document, attribute, None)
        if value and str(value).strip():
            return str(value).strip()
    return None


class DocumentIOService:
    """Serialize save/open/export through the existing Corel bridge owner."""

    def __init__(
        self,
        bridge: CorelDrawBridge = corel_bridge,
        advanced: ExtendedCorelDrawBridge = extended_bridge,
    ) -> None:
        self.bridge = bridge
        self.advanced = advanced

    def save_current(self) -> dict[str, Any]:
        """Save an already named CDR without invoking a UI Save As prompt."""

        with self.bridge.session() as (_app, document):
            current = _document_file_name(document)
            if current is None or current.casefold().startswith("untitled"):
                raise CorelDrawBridgeError(
                    "Document hiện tại chưa có đường dẫn; dùng /api/v1/design/save-as."
                )
            path = Path(current).expanduser()
            if path.suffix.casefold() != ".cdr":
                raise CorelDrawBridgeError(
                    "Document hiện tại không phải .cdr; dùng save-as với đích .cdr."
                )
            try:
                document.Save()
            except Exception as exc:
                raise CorelDrawBridgeError(
                    f"Không thể lưu document hiện tại '{path}': {exc}"
                ) from exc
        return {
            "action": "save",
            "file_path": str(path.resolve(strict=False)),
            "format": "cdr",
            "editable": True,
        }

    def save_as_cdr(self, file_path: str, *, overwrite: bool = False) -> dict[str, Any]:
        target = validate_local_path(
            file_path,
            extensions={".cdr"},
            must_exist=False,
            overwrite=overwrite,
        )
        with self.bridge.session() as (application, document):
            try:
                options = application.CreateStructSaveAsOptions()
            except AttributeError:
                # Older/fake Corel automation objects may not expose the options
                # struct. Preflight path validation still enforces overwrite.
                options = None
            try:
                if options is None:
                    document.SaveAs(str(target))
                else:
                    options.Overwrite = bool(overwrite)
                    document.SaveAs(str(target), options)
            except Exception as exc:
                raise CorelDrawBridgeError(
                    f"Không thể lưu file CDR tại '{target}': {exc}"
                ) from exc
        return {
            "action": "save_as",
            "file_path": str(target),
            "format": "cdr",
            "overwrite": overwrite,
            "editable": True,
        }

    def open_cdr(self, file_path: str) -> dict[str, Any]:
        source = validate_local_path(
            file_path,
            extensions={".cdr"},
            must_exist=True,
        )
        opened = self.bridge.open_document(str(source))
        return {
            "action": "open",
            "file_path": str(Path(opened).resolve(strict=False)),
            "format": "cdr",
            "editable": True,
        }

    def export(
        self,
        file_path: str,
        export_format: ExportFormat,
        *,
        dpi: int = 300,
        overwrite: bool = False,
    ) -> dict[str, Any]:
        target = validate_local_path(
            file_path,
            extensions={f".{export_format}"},
            must_exist=False,
            overwrite=overwrite,
        )
        exported = self.advanced.export_document(
            str(target), export_format, dpi
        )
        return {
            "action": "export",
            "file_path": str(Path(exported).resolve(strict=False)),
            "format": export_format,
            "dpi": dpi if export_format == "png" else None,
            "overwrite": overwrite,
            "editable": False,
        }


document_io = DocumentIOService()


__all__ = [
    "DocumentIOService",
    "ExportFormat",
    "document_io",
    "validate_local_path",
]
