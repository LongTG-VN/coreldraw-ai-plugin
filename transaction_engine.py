"""Atomic multi-operation execution for autonomous CorelDRAW agents."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from corel_bridge import CorelDrawBridge, CorelDrawBridgeError, corel_bridge
from design_bridge import DesignBridge
from extended_bridge import ExtendedCorelDrawBridge, extended_bridge


class DesignTransactionError(CorelDrawBridgeError):
    """Raised when a grouped design mutation fails."""

    def __init__(self, message: str, report: dict[str, Any]) -> None:
        super().__init__(message)
        self.report = report


class DesignTransactionEngine:
    """Execute an agent design plan as one CorelDRAW undoable command group."""

    def __init__(
        self,
        bridge: CorelDrawBridge = corel_bridge,
        design: DesignBridge | None = None,
        advanced: ExtendedCorelDrawBridge = extended_bridge,
    ) -> None:
        self.bridge = bridge
        self.design = design or DesignBridge(bridge)
        self.advanced = advanced

    @staticmethod
    def _require(operation: dict[str, Any], key: str) -> Any:
        value = operation.get(key)
        if value is None or (isinstance(value, str) and not value.strip()):
            raise CorelDrawBridgeError(f"Operation thiếu trường bắt buộc '{key}'.")
        return value

    @staticmethod
    def _color(operation: dict[str, Any]) -> tuple[int, int, int, int]:
        payload = operation.get("color") or {}
        if not isinstance(payload, dict):
            raise CorelDrawBridgeError("color phải là object CMYK.")
        values = (
            int(payload.get("cyan", 0)),
            int(payload.get("magenta", 0)),
            int(payload.get("yellow", 0)),
            int(payload.get("black", 0)),
        )
        if any(value < 0 or value > 100 for value in values):
            raise CorelDrawBridgeError("CMYK phải nằm trong khoảng 0..100.")
        return values

    def _execute_operation(self, operation: dict[str, Any]) -> Any:
        op = str(self._require(operation, "op")).strip().lower()

        if op == "transform":
            return self.design.transform_shape(
                str(self._require(operation, "shape_name")),
                x=operation.get("x"),
                y=operation.get("y"),
                width=operation.get("width"),
                height=operation.get("height"),
                rotation=operation.get("rotation"),
            )
        if op == "batch_transform":
            operations = operation.get("operations")
            if not isinstance(operations, list):
                raise CorelDrawBridgeError("batch_transform.operations phải là list.")
            return self.design.batch_transform(operations)
        if op == "duplicate":
            return self.design.duplicate_shape(
                str(self._require(operation, "shape_name")),
                offset_x=float(operation.get("offset_x", 0)),
                offset_y=float(operation.get("offset_y", 0)),
                new_name=operation.get("new_name"),
            )
        if op == "fill":
            return self.design.set_fill_cmyk(
                str(self._require(operation, "shape_name")), *self._color(operation)
            )
        if op == "typography":
            return self.design.set_typography(
                str(self._require(operation, "shape_name")),
                text=operation.get("text"),
                font_name=operation.get("font_name"),
                font_size=operation.get("font_size"),
            )
        if op == "order":
            return self.design.order_shape(
                str(self._require(operation, "shape_name")),
                str(self._require(operation, "mode")),
                relative_to=operation.get("relative_to"),
            )
        if op == "align":
            names = operation.get("shape_names")
            if not isinstance(names, list):
                raise CorelDrawBridgeError("align.shape_names phải là list.")
            return self.design.align_shapes(
                [str(name) for name in names],
                horizontal=operation.get("horizontal"),
                vertical=operation.get("vertical"),
                relative_to=str(operation.get("relative_to", "selection")),
            )
        if op == "distribute":
            names = operation.get("shape_names")
            if not isinstance(names, list):
                raise CorelDrawBridgeError("distribute.shape_names phải là list.")
            return self.design.distribute_shapes(
                [str(name) for name in names],
                axis=str(self._require(operation, "axis")),
                mode=str(operation.get("mode", "gaps")),
            )
        if op == "page_resize":
            return self.design.set_page_size(
                float(self._require(operation, "width")),
                float(self._require(operation, "height")),
            )
        if op == "fit_to_frame":
            return self.design.fit_shape_to_frame(
                str(self._require(operation, "shape_name")),
                str(self._require(operation, "frame_shape_name")),
                mode=str(operation.get("mode", "cover")),
                powerclip=bool(operation.get("powerclip", False)),
                lock_contents=bool(operation.get("lock_contents", True)),
            )
        if op == "delete":
            return self.design.delete_shape(str(self._require(operation, "shape_name")))
        if op == "import_asset":
            return self.design.import_asset(
                str(self._require(operation, "file_path")),
                name=operation.get("name"),
                x=operation.get("x"),
                y=operation.get("y"),
                width=operation.get("width"),
                height=operation.get("height"),
            )
        if op == "create_rectangle":
            return {
                "shape_name": self.bridge.create_rectangle_cmyk(
                    float(self._require(operation, "x")),
                    float(self._require(operation, "y")),
                    float(self._require(operation, "width")),
                    float(self._require(operation, "height")),
                    *self._color(operation),
                    shape_name=operation.get("name"),
                )
            }
        if op == "create_ellipse":
            return {
                "shape_name": self.bridge.create_ellipse_cmyk(
                    float(self._require(operation, "x")),
                    float(self._require(operation, "y")),
                    float(self._require(operation, "width")),
                    float(self._require(operation, "height")),
                    *self._color(operation),
                    shape_name=operation.get("name"),
                )
            }
        if op == "create_text":
            return {
                "shape_name": self.bridge.create_artistic_text_cmyk(
                    str(self._require(operation, "text")),
                    float(self._require(operation, "x")),
                    float(self._require(operation, "y")),
                    str(operation.get("font_name", "Arial")),
                    float(operation.get("font_size", 24)),
                    *self._color(operation),
                    shape_name=operation.get("name"),
                )
            }
        if op == "outline":
            return {
                "shape_name": self.advanced.set_shape_outline_cmyk(
                    str(self._require(operation, "shape_name")),
                    float(self._require(operation, "width")),
                    *self._color(operation),
                )
            }
        if op == "group":
            names = operation.get("shape_names")
            if not isinstance(names, list):
                raise CorelDrawBridgeError("group.shape_names phải là list.")
            return {
                "shape_name": self.advanced.group_shapes_by_names(
                    [str(name) for name in names], operation.get("group_name")
                )
            }

        raise CorelDrawBridgeError(f"Operation không được hỗ trợ: '{op}'.")

    def feedback_context(
        self,
        *,
        preview_path: str = "storage/previews/agent-feedback.png",
        preview_dpi: int = 150,
        run_check: bool = True,
        min_font_size: float = 6.0,
        require_named_objects: bool = False,
    ) -> dict[str, Any]:
        snapshot = self.design.snapshot()
        result: dict[str, Any] = {"snapshot": snapshot}
        if run_check:
            result["check"] = self.design.check_design(
                min_font_size=min_font_size,
                require_named_objects=require_named_objects,
            )
        try:
            result["preview"] = {
                "file_path": self.advanced.export_document(
                    preview_path, "png", preview_dpi
                ),
                "dpi": preview_dpi,
            }
        except CorelDrawBridgeError as exc:
            result["preview"] = {"error": str(exc), "dpi": preview_dpi}
        return result

    def execute(
        self,
        operations: list[dict[str, Any]],
        *,
        name: str = "AI Design Transaction",
        rollback_on_error: bool = True,
        include_feedback: bool = True,
        preview_path: str = "storage/previews/agent-transaction.png",
        preview_dpi: int = 150,
        run_check: bool = True,
        min_font_size: float = 6.0,
        require_named_objects: bool = False,
    ) -> dict[str, Any]:
        if not operations:
            raise CorelDrawBridgeError("operations không được rỗng.")
        if len(operations) > 200:
            raise CorelDrawBridgeError("Tối đa 200 operations cho một transaction.")

        transaction_id = uuid4().hex
        results: list[dict[str, Any]] = []
        current_index = -1
        current_operation: dict[str, Any] | None = None
        group_started = False
        group_ended = False

        with self.bridge.session() as (_app, doc):
            try:
                doc.BeginCommandGroup(name)
                group_started = True
                for current_index, current_operation in enumerate(operations):
                    result = self._execute_operation(current_operation)
                    results.append(
                        {
                            "index": current_index,
                            "op": str(current_operation.get("op", "")),
                            "result": result,
                        }
                    )
                doc.EndCommandGroup()
                group_ended = True
            except Exception as exc:
                end_error: str | None = None
                if group_started and not group_ended:
                    try:
                        doc.EndCommandGroup()
                        group_ended = True
                    except Exception as end_exc:  # pragma: no cover - real COM guard
                        end_error = str(end_exc)

                rolled_back = False
                rollback_error: str | None = None
                if rollback_on_error and group_started and group_ended:
                    try:
                        doc.Undo()
                        rolled_back = True
                    except Exception as undo_exc:  # pragma: no cover - real COM guard
                        rollback_error = str(undo_exc)

                report = {
                    "status": "rolled_back" if rolled_back else "failed",
                    "transaction_id": transaction_id,
                    "name": name,
                    "completed_operations": len(results),
                    "failed_index": current_index,
                    "failed_operation": current_operation,
                    "error": str(exc),
                    "rolled_back": rolled_back,
                    "end_group_error": end_error,
                    "rollback_error": rollback_error,
                    "results": results,
                }
                raise DesignTransactionError(
                    f"Design transaction thất bại tại operation {current_index}: {exc}",
                    report,
                ) from exc

        response: dict[str, Any] = {
            "status": "committed",
            "transaction_id": transaction_id,
            "name": name,
            "operation_count": len(results),
            "results": results,
        }
        if include_feedback:
            response["feedback"] = self.feedback_context(
                preview_path=preview_path,
                preview_dpi=preview_dpi,
                run_check=run_check,
                min_font_size=min_font_size,
                require_named_objects=require_named_objects,
            )
        return response


transaction_engine = DesignTransactionEngine()
