"""Real CorelDRAW adapter used by the safe operator service."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from corel_bridge import CorelDrawBridge, CorelDrawBridgeError, corel_bridge
from extended_bridge import (
    CDR_CURRENT_PAGE,
    CDR_PNG,
    CDR_RGB_COLOR_IMAGE,
    ExtendedCorelDrawBridge,
    extended_bridge,
)
from training.company_archive.inspector import CompanyCdrInspector, bounded_export_size
from training.company_archive.models import CdrInspectionV1
from training.company_archive.safety import assert_source_unchanged, source_stat_guard
from transaction_engine import DesignTransactionEngine


class OperatorRuntime(Protocol):
    def create_working_copy(self, source: Path, target: Path) -> None: ...
    def open(self, path: Path) -> None: ...
    def snapshot(self, path: Path) -> CdrInspectionV1: ...
    def execute_transaction(self, operations: list[dict[str, Any]], *, name: str) -> dict[str, Any]: ...
    def undo(self) -> None: ...
    def save(self) -> None: ...
    def close(self) -> None: ...
    def export_png(self, path: Path, *, max_dimension: int, max_pixels: int) -> Path: ...
    def export_pdf(self, path: Path) -> Path: ...


class CorelOperatorRuntime:
    """Serialize all document lifecycle and mutation work through one bridge."""

    def __init__(
        self,
        bridge: CorelDrawBridge = corel_bridge,
        advanced: ExtendedCorelDrawBridge = extended_bridge,
    ) -> None:
        self.bridge = bridge
        self.advanced = advanced
        self.inspector = CompanyCdrInspector(bridge)
        self.transactions = DesignTransactionEngine(bridge=bridge, advanced=advanced)

    @staticmethod
    def _active_path(document: Any) -> Path | None:
        value = str(getattr(document, "FullFileName", "") or "")
        return Path(value).resolve() if value else None

    def create_working_copy(self, source: Path, target: Path) -> None:
        before = source_stat_guard(source)
        opened = None
        try:
            with self.bridge.session() as (application, active_document):
                if self._active_path(active_document) == source:
                    raise CorelDrawBridgeError(
                        "source CDR is already active; close it before creating a copy"
                    )
                opened = self.inspector._open_document(application, source)
                try:
                    options = application.CreateStructSaveAsOptions()
                    options.Overwrite = False
                    opened.SaveAs(str(target), options)
                finally:
                    opened.Close()
        finally:
            assert_source_unchanged(source, before)
        if not target.is_file() or target.stat().st_size == 0:
            raise CorelDrawBridgeError("Corel SaveAs produced no working-copy CDR")

    def open(self, path: Path) -> None:
        self.bridge.open_document(str(path))

    def snapshot(self, path: Path) -> CdrInspectionV1:
        guard = source_stat_guard(path)
        with self.bridge.session() as (application, document):
            active = self._active_path(document)
            if active != path.resolve():
                raise CorelDrawBridgeError(
                    f"operator expected active working copy but Corel exposed: {active}"
                )
            return self.inspector._inspect_opened(application, document, path, guard)

    def execute_transaction(
        self, operations: list[dict[str, Any]], *, name: str
    ) -> dict[str, Any]:
        return self.transactions.execute(
            operations,
            name=name,
            rollback_on_error=True,
            include_feedback=False,
        )

    def undo(self) -> None:
        with self.bridge.session() as (_application, document):
            document.Undo()

    def save(self) -> None:
        with self.bridge.session() as (_application, document):
            document.Save()

    def close(self) -> None:
        with self.bridge.session() as (_application, document):
            document.Close()

    def export_png(
        self,
        path: Path,
        *,
        max_dimension: int = 2400,
        max_pixels: int = 8_000_000,
    ) -> Path:
        if path.exists():
            raise FileExistsError(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.bridge.session() as (application, document):
            page = document.ActivePage
            width, height = bounded_export_size(
                float(page.SizeWidth),
                float(page.SizeHeight),
                max_dimension=max_dimension,
                max_pixels=max_pixels,
            )
            options = application.CreateStructExportOptions()
            palette = application.CreateStructPaletteOptions()
            options.ImageType = CDR_RGB_COLOR_IMAGE
            options.Overwrite = False
            options.ResolutionX = 96
            options.ResolutionY = 96
            options.MaintainAspect = True
            options.SizeX = width
            options.SizeY = height
            export_filter = document.ExportEx(
                str(path), CDR_PNG, CDR_CURRENT_PAGE, options, palette
            )
            export_filter.Finish()
        if not path.is_file() or path.stat().st_size == 0:
            raise CorelDrawBridgeError("Corel PNG export produced no file")
        return path

    def export_pdf(self, path: Path) -> Path:
        if path.exists():
            raise FileExistsError(path)
        exported = Path(self.advanced.export_document(str(path), "pdf")).resolve()
        if not exported.is_file() or exported.stat().st_size == 0:
            raise CorelDrawBridgeError("Corel PDF export produced no file")
        return exported


__all__ = ["CorelOperatorRuntime", "OperatorRuntime"]
