"""Operation-balanced orchestration for real working-copy reliability evidence."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from statistics import median
from typing import Any

from training.corel_operator.models import OperatorResultClass
from training.corel_operator.pilot import MutationPilotRunner
from training.corel_operator.state import OperatorStateDatabase


BALANCED_OPERATION_MODES = ("replace", "move", "resize", "multi")


def select_targeted_rows(
    census_rows: list[dict[str, Any]],
    inventory_by_file_id: dict[str, dict[str, Any]],
    *,
    operation_mode: str,
    limit: int,
    seed: str,
) -> list[dict[str, Any]]:
    """Select a reproducible affected-case cohort before execution begins."""

    if operation_mode not in BALANCED_OPERATION_MODES:
        raise ValueError("unsupported targeted operation mode")
    if limit < 1:
        raise ValueError("targeted pilot limit must be positive")
    eligible: list[dict[str, Any]] = []
    for state_row in census_rows:
        result = state_row["result"]
        counts = result.get("counts", {})
        inventory = inventory_by_file_id.get(str(state_row["file_id"]))
        if (
            inventory is None
            or not bool(result.get("operator_eligible"))
            or int(counts.get("objects", 0)) <= int(counts.get("pasteboard", 0))
        ):
            continue
        if operation_mode == "replace" and int(counts.get("text", 0)) < 1:
            continue
        eligible.append(inventory)
    return sorted(
        eligible,
        key=lambda row: hashlib.sha256(
            f"{seed}:{operation_mode}:{row['file_id']}".encode("utf-8")
        ).hexdigest(),
    )[:limit]


def select_balanced_rows(
    census_rows: list[dict[str, Any]],
    inventory_by_file_id: dict[str, dict[str, Any]],
    *,
    limit_per_mode: int,
    seed: str,
) -> dict[str, list[dict[str, Any]]]:
    """Select deterministic mode-specific samples without hiding ineligible rows."""

    if limit_per_mode < 1:
        raise ValueError("limit_per_mode must be positive")
    eligible: list[dict[str, Any]] = []
    for state_row in census_rows:
        result = state_row["result"]
        inventory = inventory_by_file_id.get(str(state_row["file_id"]))
        counts = result.get("counts", {})
        if (
            inventory is not None
            and bool(result.get("operator_eligible"))
            and int(counts.get("objects", 0)) > int(counts.get("pasteboard", 0))
        ):
            eligible.append(inventory)

    selected: dict[str, list[dict[str, Any]]] = {}
    used_file_ids: set[str] = set()
    for mode in BALANCED_OPERATION_MODES:
        ordered = sorted(
            eligible,
            key=lambda row: hashlib.sha256(
                f"{seed}:{mode}:{row['file_id']}".encode("utf-8")
            ).hexdigest(),
        )
        fresh = [row for row in ordered if str(row["file_id"]) not in used_file_ids]
        reused = [row for row in ordered if str(row["file_id"]) in used_file_ids]
        chosen = (fresh + reused)[:limit_per_mode]
        selected[mode] = chosen
        used_file_ids.update(str(row["file_id"]) for row in chosen)
    return selected


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(len(ordered) * percentile + 0.999) - 1))
    return ordered[index]


def summarize_balanced_results(
    mode_payloads: dict[str, list[dict[str, Any]]],
    *,
    expected_per_mode: dict[str, int],
    selection_seed: str,
) -> dict[str, Any]:
    """Aggregate actual task outcomes without treating unsupported as success."""

    all_payloads = [item for mode in BALANCED_OPERATION_MODES for item in mode_payloads[mode]]
    counts = Counter(str(item.get("result")) for item in all_payloads)
    completed_classes = {
        OperatorResultClass.AUTO_SUCCESS.value,
        OperatorResultClass.SUCCESS_WITH_WARNING.value,
        OperatorResultClass.NEEDS_REVIEW.value,
    }
    # Match the established Run #2 denominator: an executed task is one that
    # reached a persisted editable output (AUTO/SUCCESS/REVIEW), not a
    # transaction that was subsequently rolled back by postconditions.
    executed = [
        item for item in all_payloads if str(item.get("result")) in completed_classes
    ]
    save_reopen_pass = sum(bool(item.get("editability_verified")) for item in executed)
    transaction_started = [
        item for item in all_payloads if bool(item.get("transaction_committed"))
    ]
    elapsed = [
        float(item["elapsed_seconds"])
        for item in all_payloads
        if item.get("elapsed_seconds") is not None
    ]
    unique_sources = {str(item.get("source_token")) for item in all_payloads}
    by_mode: dict[str, dict[str, Any]] = {}
    for mode in BALANCED_OPERATION_MODES:
        payloads = mode_payloads[mode]
        mode_counts = Counter(str(item.get("result")) for item in payloads)
        mode_executed = [
            item for item in payloads if str(item.get("result")) in completed_classes
        ]
        by_mode[mode] = {
            "attempted": len(payloads),
            "expected": expected_per_mode[mode],
            "auto_success": mode_counts[OperatorResultClass.AUTO_SUCCESS.value],
            "success_with_warning": mode_counts[
                OperatorResultClass.SUCCESS_WITH_WARNING.value
            ],
            "needs_review": mode_counts[OperatorResultClass.NEEDS_REVIEW.value],
            "unsupported": mode_counts[OperatorResultClass.UNSUPPORTED.value],
            "failed": mode_counts[OperatorResultClass.FAILED.value],
            "executed": len(mode_executed),
            "transactions_started": sum(
                bool(item.get("transaction_committed")) for item in payloads
            ),
            "save_reopen_pass": sum(
                bool(item.get("editability_verified")) for item in mode_executed
            ),
        }
    return {
        "schema_version": "1.0",
        "selection_seed": selection_seed,
        "planner_is_ai": False,
        "operation_modes": list(BALANCED_OPERATION_MODES),
        "tasks_total": len(all_payloads),
        "unique_source_count": len(unique_sources),
        "source_reuse_count": len(all_payloads) - len(unique_sources),
        "auto_success": counts[OperatorResultClass.AUTO_SUCCESS.value],
        "success_with_warning": counts[OperatorResultClass.SUCCESS_WITH_WARNING.value],
        "needs_review": counts[OperatorResultClass.NEEDS_REVIEW.value],
        "unsupported": counts[OperatorResultClass.UNSUPPORTED.value],
        "failed": counts[OperatorResultClass.FAILED.value],
        "executed": len(executed),
        "transactions_started": len(transaction_started),
        "save_reopen_pass": save_reopen_pass,
        "save_reopen_fail": len(executed) - save_reopen_pass,
        "source_mutations": sum(
            not bool(item.get("source_unchanged")) for item in all_payloads
        ),
        "median_seconds": median(elapsed) if elapsed else None,
        "p90_seconds": _percentile(elapsed, 0.90),
        "p95_seconds": _percentile(elapsed, 0.95),
        "by_operation": by_mode,
    }


def run_balanced_pilot(
    *,
    selected: dict[str, list[dict[str, Any]]],
    archive_root: Path,
    workspace: Path,
    timeout_seconds: float,
    selection_seed: str,
) -> dict[str, Any]:
    workspace = workspace.resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    payloads: dict[str, list[dict[str, Any]]] = {}
    for mode in BALANCED_OPERATION_MODES:
        mode_workspace = workspace / mode
        runner = MutationPilotRunner(
            archive_root=archive_root,
            workspace=mode_workspace,
            timeout_seconds=timeout_seconds,
            planner_mode=mode,
        )
        runner.run(selected[mode])
        state = OperatorStateDatabase(mode_workspace / "mutation_pilot.sqlite")
        payloads[mode] = [
            row["result"] for row in state.batch_rows("real-mutation-pilot-001")
        ]
    summary = summarize_balanced_results(
        payloads,
        expected_per_mode={mode: len(selected[mode]) for mode in BALANCED_OPERATION_MODES},
        selection_seed=selection_seed,
    )
    (workspace / "balanced_pilot_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    return summary


__all__ = [
    "BALANCED_OPERATION_MODES",
    "run_balanced_pilot",
    "select_balanced_rows",
    "select_targeted_rows",
    "summarize_balanced_results",
]
