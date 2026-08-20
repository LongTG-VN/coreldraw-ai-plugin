"""Real working-copy rollback verification for the Corel transaction engine."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from training.company_archive.inspector import CompanyCdrInspector
from training.company_archive.safety import assert_source_unchanged, resolve_source_file, source_stat_guard
from training.corel_operator.planner import DeterministicSafePilotPlanner
from training.corel_operator.policy import source_token, validate_working_copy_path
from training.corel_operator.runtime import CorelOperatorRuntime
from transaction_engine import DesignTransactionError


def _stable_snapshot(inspection) -> list[dict[str, Any]]:
    return [
        {
            "object_id": item.object_id,
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
            "fill": item.fill,
        }
        for item in inspection.objects
    ]


def verify_real_transaction_rollback(
    *,
    source_path: Path,
    archive_root: Path,
    workspace: Path,
    runtime: CorelOperatorRuntime | None = None,
) -> dict[str, Any]:
    runtime = runtime or CorelOperatorRuntime()
    source = resolve_source_file(source_path, archive_root, suffixes={".cdr", ".cdt"})
    guard = source_stat_guard(source)
    token = source_token(source, archive_root)
    target = validate_working_copy_path(
        workspace / "rollback" / token.removeprefix("source:") / "working_copy.cdr",
        workspace,
        source,
    )
    opened = False
    try:
        inspection = CompanyCdrInspector(runtime.bridge).inspect(
            source, archive_root=archive_root
        )
        plan = DeterministicSafePilotPlanner().plan(inspection, source_token=token)
        if plan is None:
            return {
                "source_token": token,
                "status": "UNSUPPORTED",
                "reason": "no unique editable text target",
                "source_unchanged": True,
            }
        action = plan.actions[0]
        object_id = action.target.value
        target_object = next(item for item in inspection.objects if item.object_id == object_id)
        runtime.create_working_copy(source, target)
        runtime.open(target)
        opened = True
        before = runtime.snapshot(target)
        caught: DesignTransactionError | None = None
        try:
            runtime.execute_transaction(
                [
                    {
                        "op": "typography",
                        "shape_name": target_object.corel_name,
                        "font_size": float(action.value),
                    },
                    {
                        "op": "typography",
                        "shape_name": "__operator_intentional_missing_target__",
                        "font_size": float(action.value),
                    },
                ],
                name="Corel Operator Intentional Rollback Verification",
            )
        except DesignTransactionError as exc:
            caught = exc
        after = runtime.snapshot(target)
        rolled_back = caught is not None and bool(caught.report.get("rolled_back"))
        snapshot_restored = _stable_snapshot(before) == _stable_snapshot(after)
        return {
            "source_token": token,
            "status": "VERIFIED" if rolled_back and snapshot_restored else "FAILED",
            "intentional_failure_observed": caught is not None,
            "transaction_reported_rollback": rolled_back,
            "snapshot_restored": snapshot_restored,
            "object_count_before": before.object_count,
            "object_count_after": after.object_count,
            "source_unchanged": True,
        }
    finally:
        if opened:
            runtime.close()
        assert_source_unchanged(source, guard)


def write_rollback_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
