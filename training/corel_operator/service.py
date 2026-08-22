"""Working-copy-only execution of bounded structured Corel mutation plans."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from training.company_archive.models import CdrInspectionV1, CdrObjectV1
from training.company_archive.safety import assert_source_unchanged, resolve_source_file, source_stat_guard
from training.corel_operator.models import (
    MutationActionV1,
    MutationPlanV1,
    OperationKind,
    MutationDependencyKind,
    OperatorExecutionResultV1,
    OperatorResultClass,
    ResolvedTargetV1,
)
from training.corel_operator.visual_qa_v2 import compare_visual_integrity_v2
from training.corel_operator.policy import (
    OperatorPolicyError,
    sanitize_error,
    source_token,
    validate_working_copy_path,
)
from training.corel_operator.runtime import (
    CanonicalExportError,
    CorelOperatorRuntime,
    OperatorRuntime,
)
from training.corel_operator.targets import TargetResolutionError, resolve_target


class CanonicalTargetOutsidePageError(RuntimeError):
    """Raised when page-anchored raster QA cannot see the requested target."""


def _object_intersects_page(
    inspection: CdrInspectionV1,
    item: CdrObjectV1,
) -> bool:
    raw = item.metadata.get("source_raw_bbox")
    if not isinstance(raw, dict):
        return not bool(item.metadata.get("bbox_clipped_to_page", False))
    left = float(raw.get("left", 0.0))
    bottom = float(raw.get("bottom", 0.0))
    right = left + float(raw.get("width", 0.0))
    top = bottom + float(raw.get("height", 0.0))
    page_left = float(inspection.page_left)
    page_bottom = float(inspection.page_bottom)
    page_right = page_left + float(inspection.page_width)
    page_top = page_bottom + float(inspection.page_height)
    return (
        max(left, page_left) < min(right, page_right)
        and max(bottom, page_bottom) < min(top, page_top)
    )


def _target_state_persisted(
    after: CdrObjectV1,
    reopened: CdrObjectV1,
    *,
    tolerance: float = 0.01,
) -> bool:
    if after.object_type != reopened.object_type:
        return False
    for field in ("text", "font_family", "alignment", "fill", "stroke"):
        if getattr(after, field) != getattr(reopened, field):
            return False
    if after.font_size is None or reopened.font_size is None:
        if after.font_size != reopened.font_size:
            return False
    elif abs(float(after.font_size) - float(reopened.font_size)) > tolerance:
        return False
    if abs(float(after.rotation) - float(reopened.rotation)) > tolerance:
        return False
    return all(
        abs(float(after.bbox[key]) - float(reopened.bbox[key])) <= tolerance
        for key in ("x", "y", "width", "height")
    )


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
        before.page_left,
        before.page_bottom,
        before.unit,
        before.corel_unit_code,
    )
    document_state_after = (
        after.page_count,
        after.page_width,
        after.page_height,
        after.page_left,
        after.page_bottom,
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
        target_item = before_map.get(target.object_id)
        for dependency in action.dependencies:
            dependency_item = before_map.get(dependency.object_id)
            if dependency_item is None:
                errors.append(f"declared dependency {dependency.object_id} is missing")
                continue
            if dependency.kind == MutationDependencyKind.DEPENDENT_CONTAINER:
                if target_item is None or target_item.parent_id != dependency.object_id:
                    errors.append(
                        f"declared dependency {dependency.object_id} is not the direct parent "
                        f"of target {target.object_id}"
                    )
                    continue
            elif dependency.kind == MutationDependencyKind.DEPENDENT_TEXT_FRAME:
                if target_item is None or dependency.object_id != target.object_id:
                    errors.append(
                        f"declared text-frame dependency {dependency.object_id} does not match "
                        f"target {target.object_id}"
                    )
                    continue
            allowed.setdefault(dependency.object_id, set()).update(
                dependency.allowed_properties
            )
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
    for action, target in zip(actions, targets, strict=True):
        left_item = before_map.get(target.object_id)
        right_item = after_map.get(target.object_id)
        if left_item is None or right_item is None:
            continue
        tolerance = 0.01
        if action.operation == OperationKind.REPLACE_TEXT and right_item.text != action.value:
            errors.append(f"target {target.object_id} text did not reach requested value")
        elif action.operation == OperationKind.SET_FONT and right_item.font_family != action.value:
            errors.append(f"target {target.object_id} font did not reach requested value")
        elif action.operation == OperationKind.SET_FONT_SIZE:
            if right_item.font_size is None or abs(right_item.font_size - float(action.value)) > tolerance:
                errors.append(f"target {target.object_id} font size missed requested value")
        elif action.operation == OperationKind.MOVE:
            value = dict(action.value)  # type: ignore[arg-type]
            if (
                abs(right_item.bbox["x"] - float(value["x"])) > tolerance
                or abs(right_item.bbox["y"] - float(value["y"])) > tolerance
                or abs(right_item.bbox["width"] - left_item.bbox["width"]) > tolerance
                or abs(right_item.bbox["height"] - left_item.bbox["height"]) > tolerance
            ):
                errors.append(f"target {target.object_id} move postcondition failed")
        elif action.operation == OperationKind.RESIZE:
            value = dict(action.value)  # type: ignore[arg-type]
            if (
                abs(right_item.bbox["width"] - float(value["width"])) > tolerance
                or abs(right_item.bbox["height"] - float(value["height"])) > tolerance
            ):
                errors.append(f"target {target.object_id} resize postcondition failed")
        elif action.operation == OperationKind.ROTATE:
            if abs(right_item.rotation - float(action.value)) > tolerance:
                errors.append(f"target {target.object_id} rotation postcondition failed")
    return errors


def _operation_payload(
    action: MutationActionV1,
    target: ResolvedTargetV1,
    before_item: CdrObjectV1,
) -> dict[str, Any]:
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
            "delta_x": float(value["x"]) - before_item.bbox["x"],
            # Inspector uses page-top Y; Corel Move uses positive Y upward.
            "delta_y": before_item.bbox["y"] - float(value["y"]),
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
            ensure_ids = getattr(self.runtime, "ensure_stable_object_ids", None)
            requested_ids = [
                action.target.value
                for action in plan.actions
                if action.target.kind.value == "object_id"
            ] + [
                dependency.object_id
                for action in plan.actions
                for dependency in action.dependencies
            ]
            object_id_aliases = ensure_ids(requested_ids) if callable(ensure_ids) else {}
            before = self.runtime.snapshot(target)
            result.object_count_before = before.object_count

            targets: list[ResolvedTargetV1] = []
            normalized_actions: list[MutationActionV1] = []
            for action in plan.actions:
                selector = action.target
                if selector.kind.value == "object_id" and selector.value in object_id_aliases:
                    selector = selector.model_copy(
                        update={"value": object_id_aliases[selector.value]}
                    )
                resolved = resolve_target(before.objects, selector)
                if action.precondition_object_type and resolved.object_type != action.precondition_object_type:
                    raise TargetResolutionError(
                        f"target type is {resolved.object_type}, expected {action.precondition_object_type}"
                    )
                targets.append(resolved)
                dependencies = [
                    dependency.model_copy(
                        update={
                            "object_id": object_id_aliases.get(
                                dependency.object_id,
                                dependency.object_id,
                            )
                        }
                    )
                    for dependency in action.dependencies
                ]
                normalized_actions.append(
                    action.model_copy(
                        update={"target": selector, "dependencies": dependencies}
                    )
                )
            result.resolved_targets = targets
            result.metadata["stable_id_alias_count"] = sum(
                old != new for old, new in object_id_aliases.items()
            )
            before_map = {item.object_id: item for item in before.objects}
            outside_page = [
                resolved.object_id
                for resolved in targets
                if not _object_intersects_page(before, before_map[resolved.object_id])
            ]
            if outside_page:
                raise CanonicalTargetOutsidePageError(
                    "page-anchored visual QA cannot observe target objects on "
                    "the pasteboard"
                )

            before_preview = target.with_name(target.stem + "_before.png")
            before_export = self.runtime.export_canonical_png(
                before_preview,
                dpi=200,
                max_dimension=2400,
                max_pixels=8_000_000,
            )
            result.preview_before = str(before_preview)

            transaction_started = time.perf_counter()
            operations = [
                _operation_payload(
                    action,
                    resolved,
                    next(item for item in before.objects if item.object_id == resolved.object_id),
                )
                for action, resolved in zip(normalized_actions, targets, strict=True)
            ]
            self.runtime.execute_transaction(operations, name=f"Corel Operator: {plan.plan_id}")
            result.transaction_committed = True
            result.operation_count = len(operations)
            result.timings_ms["transaction"] = (
                time.perf_counter() - transaction_started
            ) * 1000

            after = self.runtime.snapshot(target)
            result.object_count_after = after.object_count
            scope_errors = _validate_mutation_scope(before, after, normalized_actions, targets)
            if scope_errors:
                self.runtime.undo()
                rolled_back = self.runtime.snapshot(target)
                result.rollback_verified = all(
                    _tracked_state(left) == _tracked_state(right)
                    for left, right in zip(before.objects, rolled_back.objects, strict=True)
                )
                raise OperatorPolicyError("; ".join(scope_errors))

            after_preview = target.with_name(target.stem + "_after.png")
            try:
                after_export = self.runtime.export_canonical_png(
                    after_preview,
                    dpi=200,
                    max_dimension=2400,
                    max_pixels=8_000_000,
                )
            except CanonicalExportError:
                self.runtime.undo()
                rolled_back = self.runtime.snapshot(target)
                result.rollback_verified = all(
                    _tracked_state(left) == _tracked_state(right)
                    for left, right in zip(before.objects, rolled_back.objects, strict=True)
                )
                raise
            result.preview_after = str(after_preview)
            visual_qa = compare_visual_integrity_v2(
                before,
                after,
                before_export,
                after_export,
                target_ids=[item.object_id for item in targets],
                structural_errors=scope_errors,
            )
            result.metadata["canonical_export_before"] = before_export.model_dump(mode="json")
            result.metadata["canonical_export_after"] = after_export.model_dump(mode="json")
            result.metadata["visual_qa_v2"] = visual_qa.model_dump(mode="json")
            # Preserve the established metadata key for batch/MCP consumers.
            result.metadata["visual_qa"] = visual_qa.model_dump(mode="json")
            (target.parent / "visual_qa_v2.json").write_text(
                json.dumps(visual_qa.model_dump(mode="json"), indent=2),
                encoding="utf-8",
            )
            if visual_qa.status == "FAIL":
                self.runtime.undo()
                rolled_back = self.runtime.snapshot(target)
                result.rollback_verified = all(
                    _tracked_state(left) == _tracked_state(right)
                    for left, right in zip(before.objects, rolled_back.objects, strict=True)
                )
                raise OperatorPolicyError(
                    "visual integrity failure: " + ",".join(visual_qa.reasons)
                )

            self.runtime.save()
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
            after_map = {item.object_id: item for item in after.objects}
            reopened_map = {item.object_id: item for item in reopened.objects}
            target_ids = {item.object_id for item in targets}
            persisted_targets = all(
                object_id in after_map
                and object_id in reopened_map
                and _target_state_persisted(
                    after_map[object_id],
                    reopened_map[object_id],
                )
                for object_id in target_ids
            )
            identity_drift = set(after_map).symmetric_difference(reopened_map)
            result.metadata["reopen_identity_drift_count"] = len(identity_drift)
            result.editability_verified = (
                reopened.object_count == after.object_count
                and persisted_targets
            )
            if not result.editability_verified:
                raise OperatorPolicyError("working copy failed editable reopen verification")
            self.runtime.close()
            document_open = False
            if visual_qa.status == "NEEDS_REVIEW":
                result.result = OperatorResultClass.NEEDS_REVIEW
                result.warnings.extend(visual_qa.reasons)
            else:
                result.result = OperatorResultClass.AUTO_SUCCESS
        except TargetResolutionError as exc:
            result.result = OperatorResultClass.NEEDS_REVIEW
            result.error_code = "TARGET_NOT_UNIQUE_OR_MISSING"
            result.error = sanitize_error(exc, archive_root=archive_root)
        except CanonicalTargetOutsidePageError as exc:
            result.result = OperatorResultClass.NEEDS_REVIEW
            result.error_code = "TARGET_OUTSIDE_CANONICAL_PAGE"
            result.error = sanitize_error(exc, archive_root=archive_root)
        except CanonicalExportError as exc:
            result.result = OperatorResultClass.NEEDS_REVIEW
            result.error_code = "CANONICAL_EXPORT_FAILED"
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
