from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import main
from corel_bridge import CorelDrawBridgeError
from document_io import DocumentIOService, validate_local_path


class _SaveOptions:
    Overwrite = False


class _Application:
    def __init__(self) -> None:
        self.options = _SaveOptions()

    def CreateStructSaveAsOptions(self) -> _SaveOptions:
        return self.options


class _Document:
    def __init__(self, file_name: str | None = None) -> None:
        self.FullFileName = file_name or ""
        self.save_count = 0
        self.save_as_calls: list[tuple[str, bool]] = []

    def Save(self) -> None:
        self.save_count += 1

    def SaveAs(self, file_name: str, options: _SaveOptions) -> None:
        self.save_as_calls.append((file_name, bool(options.Overwrite)))
        Path(file_name).write_bytes(b"fake-cdr")
        self.FullFileName = file_name


class _Bridge:
    def __init__(self, document: _Document) -> None:
        self.application = _Application()
        self.document = document
        self.opened: list[str] = []

    @contextmanager
    def session(self):
        yield self.application, self.document

    def open_document(self, file_name: str) -> str:
        self.opened.append(file_name)
        return file_name


class _Advanced:
    def __init__(self) -> None:
        self.exports: list[tuple[str, str, int]] = []

    def export_document(self, file_name: str, export_format: str, dpi: int) -> str:
        self.exports.append((file_name, export_format, dpi))
        Path(file_name).write_bytes(b"fake-export")
        return file_name


def _service(document: _Document) -> tuple[DocumentIOService, _Bridge, _Advanced]:
    bridge = _Bridge(document)
    advanced = _Advanced()
    return DocumentIOService(bridge=bridge, advanced=advanced), bridge, advanced


def test_validate_local_path_rejects_relative_traversal_and_wrong_extension(
    tmp_path: Path,
) -> None:
    with pytest.raises(CorelDrawBridgeError, match="tuyệt đối"):
        validate_local_path(
            "output.cdr", extensions={".cdr"}, must_exist=False
        )

    traversal = tmp_path / "child" / ".." / "output.cdr"
    with pytest.raises(CorelDrawBridgeError, match=r"\.\."):
        validate_local_path(
            str(traversal), extensions={".cdr"}, must_exist=False
        )

    with pytest.raises(CorelDrawBridgeError, match="mở rộng"):
        validate_local_path(
            str(tmp_path / "output.pdf"),
            extensions={".cdr"},
            must_exist=False,
        )


def test_validate_local_path_enforces_parent_existence_and_overwrite(
    tmp_path: Path,
) -> None:
    with pytest.raises(CorelDrawBridgeError, match="Thư mục đích"):
        validate_local_path(
            str(tmp_path / "missing" / "output.cdr"),
            extensions={".cdr"},
            must_exist=False,
        )

    target = tmp_path / "output.cdr"
    target.write_bytes(b"existing")
    with pytest.raises(CorelDrawBridgeError, match="overwrite=false"):
        validate_local_path(
            str(target), extensions={".cdr"}, must_exist=False
        )
    assert (
        validate_local_path(
            str(target),
            extensions={".cdr"},
            must_exist=False,
            overwrite=True,
        )
        == target.resolve()
    )


def test_save_current_requires_named_cdr_and_saves_existing_document(
    tmp_path: Path,
) -> None:
    service, _bridge, _advanced = _service(_Document("Untitled-1"))
    with pytest.raises(CorelDrawBridgeError, match="save-as"):
        service.save_current()

    cdr_path = tmp_path / "named.cdr"
    document = _Document(str(cdr_path))
    service, _bridge, _advanced = _service(document)
    result = service.save_current()
    assert document.save_count == 1
    assert result["file_path"] == str(cdr_path.resolve())
    assert result["editable"] is True


def test_save_as_open_and_export_use_strict_paths(tmp_path: Path) -> None:
    document = _Document()
    service, bridge, advanced = _service(document)

    cdr_path = tmp_path / "design.cdr"
    saved = service.save_as_cdr(str(cdr_path))
    assert cdr_path.read_bytes() == b"fake-cdr"
    assert document.save_as_calls == [(str(cdr_path.resolve()), False)]
    assert saved["format"] == "cdr"
    assert saved["editable"] is True

    opened = service.open_cdr(str(cdr_path))
    assert bridge.opened == [str(cdr_path.resolve())]
    assert opened["action"] == "open"

    png_path = tmp_path / "preview.png"
    exported = service.export(str(png_path), "png", dpi=150)
    assert advanced.exports == [(str(png_path.resolve()), "png", 150)]
    assert exported["format"] == "png"
    assert exported["editable"] is False


def test_design_document_routes_preserve_legacy_routes(monkeypatch, tmp_path: Path) -> None:
    class _Service:
        def save_current(self):
            return {"action": "save", "file_path": "D:/named.cdr"}

        def save_as_cdr(self, path: str, *, overwrite: bool = False):
            return {"action": "save_as", "file_path": path, "overwrite": overwrite}

        def open_cdr(self, path: str):
            return {"action": "open", "file_path": path}

        def export(self, path: str, export_format: str, *, dpi: int, overwrite: bool):
            return {
                "action": "export",
                "file_path": path,
                "format": export_format,
                "dpi": dpi,
                "overwrite": overwrite,
            }

    monkeypatch.setattr(main, "document_io", _Service())
    client = TestClient(main.app)

    assert client.post("/api/v1/design/save").status_code == 200
    save_as = client.post(
        "/api/v1/design/save-as",
        json={"path": str(tmp_path / "api.cdr")},
    )
    assert save_as.status_code == 200
    assert save_as.json()["overwrite"] is False
    assert client.post(
        "/api/v1/design/export",
        json={"format": "pdf", "path": str(tmp_path / "api.pdf")},
    ).status_code == 200

    paths = {route.path for route in main.app.routes}
    assert "/api/v1/corel/document/save" in paths
    assert "/api/v1/corel/document/open" in paths
    assert "/api/v1/corel/export" in paths
