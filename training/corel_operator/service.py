"""Working-copy-only execution of bounded structured Corel mutation plans."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from training.company_archive.models import CdrInspectionV1, CdrObjectV1
from training.company_archive.safety import assert_source_unchanged, resolve_source_file, source_stat_guard
from training.corel_operator.models import (
    MutationActionV1,
    MutationPlanV1,
    OperationKind,
    OperatorExecutionResultV1,
    OperatorResultClass,
    ResolvedTargetV1,
)
from training.corel_operator.policy import (
    OperatorPolicyError,
    sanitize_error,
    source_token,
    validate_working_copy_path,
)
from training.corel_operator.runtime import CorelOperatorRuntime, OperatorRuntime
from training.corel_operator.targets import TargetResolutionError, resolve_target


def _tracked_state(item: CdrObjectV1) -> dict[str, Any]:
    return {
        "corel_name": item.corel_name,
        "object_type": item.object_type,
        "bbox": item.bbox,
        "rotation": item.rotation,
        "z_index": item.z_index,
        "layer": item.layer,
        "parent_id": item.parent_id,
        "text": item.text,
        "font_family": item.font_family,
        "font_size": item.font_size,
        "alignment": item.alignment,
        "fill": item.fill,
        "stroke": item.stroke,
        "outside_canvas": bool(item.metadata.get("bbox_clipped_to_page", False)),
    }


_ALLOWED_BY_OPERATION: dict[OperationKind, set[str]] = {
    OperationKind.REPLACE_TEXT: {"text", "bbox", "font_size"},
    OperationKind.MOVE: {"bbox"},
    OperationKind.RESIZE: {"bbox"},
    OperationKind.ROTATE: {"bbox", "rotation"},
    OperationKind.SET_FONT: {"font_family", "bbox"},
    OperationKind.SET_FONT_SIZE: {"font_size", "bbox"},
}


def _validate_mutation_scope(
    before: CdrInspectionV1,
    after: CdrInspectionV1,
    actions: list[MutationActionV1],
    targets: list[ResolvedTargetV1],
) -> list[str]:
    errors: list[str] = []
    document_state_before = (
        before.page_count,
        before.page_width,
        before.page_height,
        before.unit,
        before.corel_unit_code,
    )
    document_state_after = (
        after.page_count,
        after.page_width,
        after.page_height,
        after.unit,
        after.corel_unit_code,
    )
    if document_state_before != document_state_after:
        errors.append("document page geometry or units changed outside policy")
    if before.object_count != after.object_count:
        errors.append(
            f"object count changed from {before.object_count} to {after.object_count}"
        )
    before_map = {item.object_id: item for item in before.objects}
    after_map = {item.object_id: item for item in after.objects}
    if set(before_map) != set(after_map):
        errors.append("object identity set changed")
        return errors
    allowed: dict[str, set[str]] = {}
    for action, target in zip(actions, targets, strict=True):
        allowed.setdefault(target.object_id, set()).update(_ALLOWED_BY_OPERATION[action.operation])
        allowed[target.object_id].update(action.allowed_properties)
    for object_id, before_item in before_map.items():
        left = _tracked_state(before_item)
        right = _tracked_state(after_map[object_id])
        permitted = allowed.get(object_id, set())
        changed = {name for name in left if left[name] != right[name]}
        unexpected = changed - permitted
        if unexpected:
            errors.append(
                f"object {object_id} changed outside policy: {','.join(sorted(unexpected))}"
            )
    return errors


def _operation_payload(action: MutationActionV1, target: ResolvedTargetV1) -> dict[str, Any]:
    name = target.corel_name
    if action.operation == OperationKind.REPLACE_TEXT:
        return {
            "op": "typography",
            "shape_name": name,
            "operator_object_id": target.object_id,
            "text": str(action.value),
        }
    if action.operation == OperationKind.SET_FONT:
        return {
            "op": "typography",
            "shape_name": name,
            "operator_object_id": target.object_id,
            "font_name": str(action.value),
        }
    if action.operation == OperationKind.SET_FONT_SIZE:
        return {
            "op": "typography",
            "shape_name": name,
            "operator_object_id": target.object_id,
            "font_size": float(action.value),
        }
    if action.operation == OperationKind.MOVE:
        value = dict(action.value)  # type: ignore[arg-type]
        return {
            "op": "transform",
            "shape_name": name,
            "operator_object_id": target.object_id,
            "x": value["x"],
            "y": value["y"],
        }
    if action.operation == OperationKind.RESIZE:
        value = dict(action.value)  # type: ignore[arg-type]
        return {
            "op": "transform",
            "shape_name": name,
            "operator_object_id": target.object_id,
            "width": value["width"],
            "height": value["height"],
        }
    if action.operation == OperationKind.ROTATE:
        return {
            "op": "transform",
            "shape_name": name,
            "operator_object_id": target.object_id,
            "rotation": float(action.value),
        }
    raise OperatorPolicyError(f"unsupported operation: {action.operation.value}")


class SafeCorelOperator:
    """Execute plans only on Corel-created CDR copies with postcondition checks."""

    def __init__(self, runtime: OperatorRuntime | None = None) -> None:
        self.runtime = runtime or CorelOperatorRuntime()

    def execute(
        self,
        *,
        source_path: Path,
        archive_root: Path,
        workspace: Path,
        working_copy_path: Path,
        plan: MutationPlanV1,
        export_pdf: bool = True,
    ) -> OperatorExecutionResultV1:
        started = time.perf_counter()
        source = resolve_source_file(source_path, archive_root, suffixes={".cdr", ".cdt"})
        token = source_token(source, archive_root)
        source_before = source_stat_guard(source)
        result = OperatorExecutionResultV1(
            result=OperatorResultClass.FAILED,
            plan_id=plan.plan_id,
            source_token=token,
            source_unchanged=False,
        )
        target = None
        document_open = False
        try:
            target = validate_working_copy_path(working_copy_path, workspace, source)
            result.working_copy = str(target)
            copy_started = time.perf_counter()
            self.runtime.create_working_copy(source, target)
            result.timings_ms["copy"] = (time.perf_counter() - copy_started) * 1000

            self.runtime.open(target)
            document_open = True
            before = self.runtime.snapshot(target)
            result.object_count_before = before.object_count
            before_preview = target.with_name(target.stem + "_before.png")
            self.runtime.export_png(before_preview, max_dimension=2400, max_pixels=8_000_000)
            result.preview_before = str(before_preview)

            targets: list[ResolvedTargetV1] = []
            for action in plan.actions:
                resolved = resolve_target(before.objects, action.target)
                if action.precondition_object_type and resolved.object_type != action.precondition_object_type:
                    raise TargetResolutionError(
                        f"target type is {resolved.object_type}, expected {action.precondition_object_type}"
                    )
                targets.append(resolved)
            result.resolved_targets = targets

            transaction_started = time.perf_counter()
            operations = [
                _operation_payload(action, resolved)
                for action, resolved in zip(plan.actions, targets, strict=True)
            ]
            self.runtime.execute_transaction(operations, name=f"Corel Operator: {plan.plan_id}")
            result.transaction_committed = True
            result.operation_count = len(operations)
            result.timings_ms["transaction"] = (
                time.perf_counter() - transaction_started
            ) * 1000

            after = self.runtime.snapshot(target)
            result.object_count_after = after.object_count
            scope_errors = _validate_mutation_scope(before, after, plan.actions, targets)
            if scope_errors:
                self.runtime.undo()
                rolled_back = self.runtime.snapshot(target)
                result.rollback_verified = all(
                    _tracked_state(left) == _tracked_state(right)
                    for left, right in zip(before.objects, rolled_back.objects, strict=True)
                )
                raise OperatorPolicyError("; ".join(scope_errors))

            self.runtime.save()
            after_preview = target.with_name(target.stem + "_after.png")
            self.runtime.export_png(after_preview, max_dimension=2400, max_pixels=8_000_000)
            result.preview_after = str(after_preview)
            if export_pdf:
                pdf = target.with_suffix(".pdf")
                self.runtime.export_pdf(pdf)
                result.pdf_after = str(pdf)
            self.runtime.close()
            document_open = False

            self.runtime.open(target)
            document_open = True
            reopened = self.runtime.snapshot(target)
            result.reopened_object_count = reopened.object_count
            result.editability_verified = (
                reopened.object_count == after.object_count
                and {item.object_id for item in reopened.objects}
                == {item.object_id for item in after.objects}
            )
            if not result.editability_verified:
                raise OperatorPolicyError("working copy failed editable reopen verification")
            self.runtime.close()
            document_open = False
            result.result = OperatorResultClass.AUTO_SUCCESS
        except TargetResolutionError as exc:
            result.result = OperatorResultClass.NEEDS_REVIEW
            result.error_code = "TARGET_NOT_UNIQUE_OR_MISSING"
            result.error = sanitize_error(exc, archive_root=archive_root)
        except (OperatorPolicyError, ValueError, FileExistsError) as exc:
            result.result = OperatorResultClass.FAILED
            result.error_code = "POLICY_OR_VALIDATION_FAILURE"
            result.error = sanitize_error(exc, archive_root=archive_root)
        except Exception as exc:  # real COM boundaries are normalized for batch isolation
            result.result = OperatorResultClass.FAILED
            result.error_code = "COREL_RUNTIME_FAILURE"
            result.error = sanitize_error(exc, archive_root=archive_root)
        finally:
            if document_open:
                try:
                    self.runtime.close()
                except Exception as exc:
                    result.warnings.append(
                        "close failure: " + sanitize_error(exc, archive_root=archive_root)
                    )
            try:
                assert_source_unchanged(source, source_before)
                result.source_unchanged = True
            except Exception as exc:
                result.source_unchanged = False
                result.result = OperatorResultClass.FAILED
                result.error_code = "SOURCE_MUTATION_DETECTED"
                result.error = sanitize_error(exc, archive_root=archive_root)
            result.timings_ms["total"] = (time.perf_counter() - started) * 1000
        return result


__all__ = ["SafeCorelOperator", "_validate_mutation_scope"]
