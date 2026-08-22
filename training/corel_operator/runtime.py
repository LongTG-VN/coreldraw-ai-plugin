"""Real CorelDRAW adapter used by the safe operator service."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from corel_bridge import CorelDrawBridge, CorelDrawBridgeError, corel_bridge
from extended_bridge import (
    CDR_CURRENT_PAGE,
    CDR_PNG,
    CDR_RGB_COLOR_IMAGE,
    ExtendedCorelDrawBridge,
    extended_bridge,
)
from training.company_archive.inspector import COREL_UNITS, CompanyCdrInspector, bounded_export_size
from training.company_archive.models import CdrInspectionV1
from training.company_archive.safety import assert_source_unchanged, source_stat_guard
from training.corel_operator.canonical_export import (
    CanonicalExportEvidenceV1,
    canonical_export_evidence,
    canonical_page_dimensions,
)
from transaction_engine import DesignTransactionEngine, DesignTransactionError


class OperatorRuntime(Protocol):
    def create_working_copy(self, source: Path, target: Path) -> None: ...
    def open(self, path: Path) -> None: ...
    def snapshot(self, path: Path) -> CdrInspectionV1: ...
    def execute_transaction(self, operations: list[dict[str, Any]], *, name: str) -> dict[str, Any]: ...
    def undo(self) -> None: ...
    def save(self) -> None: ...
    def close(self) -> None: ...
    def export_png(self, path: Path, *, max_dimension: int, max_pixels: int) -> Path: ...
    def export_canonical_png(
        self,
        path: Path,
        *,
        dpi: int,
        max_dimension: int,
        max_pixels: int,
    ) -> CanonicalExportEvidenceV1: ...
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
        if operations and all(operation.get("operator_object_id") for operation in operations):
            return self._execute_object_transaction(operations, name=name)
        return self.transactions.execute(
            operations,
            name=name,
            rollback_on_error=True,
            include_feedback=False,
        )

    def _execute_object_transaction(
        self, operations: list[dict[str, Any]], *, name: str
    ) -> dict[str, Any]:
        """Execute the operator subset against stable traversal IDs, not names."""

        transaction_id = uuid4().hex
        results: list[dict[str, Any]] = []
        current_index = -1
        current_operation: dict[str, Any] | None = None
        with self.bridge.session() as (_application, document):
            group_started = False
            group_ended = False
            try:
                document.BeginCommandGroup(name)
                group_started = True
                for current_index, current_operation in enumerate(operations):
                    object_id = str(current_operation["operator_object_id"])
                    shape_by_id, _parent_by_id = self.inspector._shape_map(document)
                    shape = shape_by_id.get(object_id)
                    if shape is None:
                        raise CorelDrawBridgeError(
                            f"operator object ID is unavailable: {object_id}"
                        )
                    op = str(current_operation.get("op", ""))
                    if op == "typography":
                        retry_count = self._apply_typography_with_retry(
                            document,
                            object_id=object_id,
                            operation=current_operation,
                        )
                    elif op == "transform":
                        if "width" in current_operation or "height" in current_operation:
                            width = float(
                                current_operation.get("width", getattr(shape, "SizeWidth"))
                            )
                            height = float(
                                current_operation.get("height", getattr(shape, "SizeHeight"))
                            )
                            try:
                                shape.SetSize(width, height)
                            except Exception:
                                shape.SizeWidth = width
                                shape.SizeHeight = height
                        if "x" in current_operation or "y" in current_operation:
                            x = float(
                                current_operation.get(
                                    "x", getattr(shape, "LeftX", getattr(shape, "PositionX", 0))
                                )
                            )
                            y = float(
                                current_operation.get(
                                    "y", getattr(shape, "BottomY", getattr(shape, "PositionY", 0))
                                )
                            )
                            try:
                                shape.SetPosition(x, y)
                            except Exception:
                                shape.PositionX = x
                                shape.PositionY = y
                        if "rotation" in current_operation:
                            shape.RotationAngle = float(current_operation["rotation"])
                    else:
                        raise CorelDrawBridgeError(
                            f"operator object transaction does not support: {op}"
                        )
                    item_result = {"index": current_index, "op": op, "object_id": object_id}
                    if op == "typography":
                        item_result["retry_count"] = retry_count
                    results.append(item_result)
                document.EndCommandGroup()
                group_ended = True
            except Exception as exc:
                end_error = None
                if group_started and not group_ended:
                    try:
                        document.EndCommandGroup()
                        group_ended = True
                    except Exception as end_exc:
                        end_error = str(end_exc)
                rolled_back = False
                rollback_error = None
                if group_started and group_ended:
                    try:
                        document.Undo()
                        rolled_back = True
                    except Exception as undo_exc:
                        rollback_error = str(undo_exc)
                report = {
                    "status": "rolled_back" if rolled_back else "failed",
                    "transaction_id": transaction_id,
                    "name": name,
                    "completed_operations": len(results),
                    "failed_index": current_index,
                    "failed_operation": {
                        key: value
                        for key, value in (current_operation or {}).items()
                        if key not in {"text"}
                    },
                    "error": str(exc),
                    "rolled_back": rolled_back,
                    "end_group_error": end_error,
                    "rollback_error": rollback_error,
                    "results": results,
                }
                raise DesignTransactionError(
                    f"operator object transaction failed at {current_index}: {exc}",
                    report,
                ) from exc
        return {
            "status": "committed",
            "transaction_id": transaction_id,
            "name": name,
            "operation_count": len(results),
            "results": results,
        }

    @staticmethod
    def _retryable_text_range_error(exc: Exception) -> bool:
        cursor: BaseException | None = exc
        for _ in range(5):
            if cursor is None:
                break
            message = str(cursor).casefold()
            hresult = getattr(cursor, "hresult", None)
            if "textrange" in message or hresult in {-2147467259, -2147352567}:
                return True
            cursor = cursor.__cause__ or cursor.__context__
        return False

    @staticmethod
    def _apply_typography_to_shape(shape: Any, operation: dict[str, Any]) -> None:
        try:
            story = shape.Text.Story
        except Exception as exc:
            raise CorelDrawBridgeError("operator target is not editable text") from exc
        if "text" in operation:
            story.Text = str(operation["text"])
        if "font_name" in operation:
            story.Font = str(operation["font_name"])
        if "font_size" in operation:
            story.Size = float(operation["font_size"])

    def _apply_typography_with_retry(
        self,
        document: Any,
        *,
        object_id: str,
        operation: dict[str, Any],
        max_attempts: int = 2,
    ) -> int:
        """Retry only known TextRange COM failures after reacquiring the live shape."""

        for attempt in range(1, max_attempts + 1):
            shape_by_id, _parent_by_id = self.inspector._shape_map(document)
            shape = shape_by_id.get(object_id)
            if shape is None:
                raise CorelDrawBridgeError(
                    f"operator object ID is unavailable during text retry: {object_id}"
                )
            try:
                self._apply_typography_to_shape(shape, operation)
                return attempt - 1
            except Exception as exc:
                if attempt >= max_attempts or not self._retryable_text_range_error(exc):
                    raise
        raise AssertionError("bounded typography retry loop did not terminate")

    def undo(self) -> None:
        with self.bridge.session() as (_application, document):
            document.Undo()

    def save(self) -> None:
        with self.bridge.session() as (_application, document):
            document.Save()

    def close(self) -> None:
        with self.bridge.session() as (_application, document):
            document.Close()

    def close_active_if_under(self, root: Path) -> bool:
        """Close only a generated document proven to live below ``root``."""

        allowed = root.expanduser().resolve()
        with self.bridge.session() as (_application, document):
            active = self._active_path(document)
            if active is None:
                return False
            try:
                active.relative_to(allowed)
            except ValueError as exc:
                raise CorelDrawBridgeError(
                    f"refusing to close active document outside operator workspace: {active}"
                ) from exc
            document.Close()
            return True

    def close_active_if_exact(self, path: Path) -> bool:
        """Close one exact source path without Save and verify its stat guard."""

        expected = path.expanduser().resolve()
        before = source_stat_guard(expected)
        with self.bridge.session() as (_application, document):
            active = self._active_path(document)
            if active is None:
                return False
            if active != expected:
                raise CorelDrawBridgeError(
                    f"refusing to close unexpected active document: {active}"
                )
            document.Close()
        assert_source_unchanged(expected, before)
        return True

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

    def export_canonical_png(
        self,
        path: Path,
        *,
        dpi: int = 200,
        max_dimension: int = 2400,
        max_pixels: int = 8_000_000,
    ) -> CanonicalExportEvidenceV1:
        """Export the active page into an explicit page-derived pixel frame."""

        if path.exists():
            raise FileExistsError(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.bridge.session() as (application, document):
            page = document.ActivePage
            unit_code = int(getattr(document, "Unit", -1))
            unit = COREL_UNITS.get(unit_code, "unknown")
            geometry = canonical_page_dimensions(
                float(page.SizeWidth),
                float(page.SizeHeight),
                unit=unit,
                dpi=dpi,
                max_dimension=max_dimension,
                max_pixels=max_pixels,
            )
            options = application.CreateStructExportOptions()
            palette = application.CreateStructPaletteOptions()
            options.ImageType = CDR_RGB_COLOR_IMAGE
            options.Overwrite = False
            options.ResolutionX = dpi
            options.ResolutionY = dpi
            # Corel's MaintainAspect=True may replace one requested dimension
            # with an artwork/content-derived value. False preserves the exact
            # verified page-space frame supplied through SizeX/SizeY.
            options.MaintainAspect = False
            options.SizeX = geometry.width_px
            options.SizeY = geometry.height_px
            export_filter = document.ExportEx(
                str(path), CDR_PNG, CDR_CURRENT_PAGE, options, palette
            )
            export_filter.Finish()
        if not path.is_file() or path.stat().st_size == 0:
            raise CorelDrawBridgeError("Corel canonical PNG export produced no file")
        evidence = canonical_export_evidence(path, geometry)
        if not evidence.dimensions_verified:
            raise CorelDrawBridgeError(
                "Corel canonical PNG dimensions differed from the page-derived frame: "
                f"expected {geometry.width_px}x{geometry.height_px}, got "
                f"{evidence.actual_width_px}x{evidence.actual_height_px}"
            )
        return evidence

    def export_pdf(self, path: Path) -> Path:
        if path.exists():
            raise FileExistsError(path)
        exported = Path(self.advanced.export_document(str(path), "pdf")).resolve()
        if not exported.is_file() or exported.stat().st_size == 0:
            raise CorelDrawBridgeError("Corel PDF export produced no file")
        return exported


__all__ = ["CorelOperatorRuntime", "OperatorRuntime"]
