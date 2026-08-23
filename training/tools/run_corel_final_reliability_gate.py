"""Run only the prior blockers and minimum additional final-gate evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from training.company_archive.database import ArchiveDatabase
from training.corel_operator.pilot import MutationPilotRunner
from training.corel_operator.policy import source_token
from training.corel_operator.state import OperatorStateDatabase


COMPLETED_RESULTS = {"AUTO_SUCCESS", "SUCCESS_WITH_WARNING", "NEEDS_REVIEW"}


def select_additional_text_rows(
    census_rows: list[dict[str, Any]],
    inventory_by_file_id: dict[str, dict[str, Any]],
    *,
    excluded_file_ids: set[str],
    limit: int,
    seed: str,
) -> list[dict[str, Any]]:
    """Select a fixed text-capable cohort outside the previous balanced sample."""

    eligible: list[dict[str, Any]] = []
    for state_row in census_rows:
        file_id = str(state_row["file_id"])
        result = state_row["result"]
        counts = result.get("counts", {})
        inventory = inventory_by_file_id.get(file_id)
        if (
            inventory is not None
            and file_id not in excluded_file_ids
            and bool(result.get("operator_eligible"))
            and int(counts.get("objects", 0)) > int(counts.get("pasteboard", 0))
            and int(counts.get("text", 0)) > 0
        ):
            eligible.append(inventory)
    return sorted(
        eligible,
        key=lambda row: hashlib.sha256(
            f"{seed}:{row['file_id']}".encode("utf-8")
        ).hexdigest(),
    )[:limit]


def replace_prior_results(
    previous: list[dict[str, Any]],
    rerun: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Replace a prior outcome by source identity instead of double-counting it."""

    rerun_by_token = {str(item["source_token"]): item for item in rerun}
    return [rerun_by_token.get(str(item["source_token"]), item) for item in previous]


def summarize_family(payloads: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(str(item.get("result")) for item in payloads)
    executed = [item for item in payloads if item.get("result") in COMPLETED_RESULTS]
    save_reopen = sum(bool(item.get("editability_verified")) for item in executed)
    return {
        "attempted": len(payloads),
        "executed": len(executed),
        "auto_success": counts["AUTO_SUCCESS"],
        "success_with_warning": counts["SUCCESS_WITH_WARNING"],
        "needs_review": counts["NEEDS_REVIEW"],
        "unsupported": counts["UNSUPPORTED"],
        "failed": counts["FAILED"],
        "save_reopen_pass": save_reopen,
        "save_reopen_pass_rate": save_reopen / len(executed) if executed else 0.0,
        "failed_rate": counts["FAILED"] / len(payloads) if payloads else 0.0,
        "source_mutations": sum(
            not bool(item.get("source_unchanged")) for item in payloads
        ),
    }


def _payloads(workspace: Path) -> list[dict[str, Any]]:
    return [
        row["result"]
        for row in OperatorStateDatabase(
            workspace / "mutation_pilot.sqlite"
        ).batch_rows("real-mutation-pilot-001")
    ]


def _run(
    rows: list[dict[str, Any]],
    *,
    archive_root: Path,
    workspace: Path,
    mode: str,
    timeout_seconds: float,
) -> list[dict[str, Any]]:
    MutationPilotRunner(
        archive_root=archive_root,
        workspace=workspace,
        timeout_seconds=timeout_seconds,
        planner_mode=mode,
    ).run(rows)
    return _payloads(workspace)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive-root", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--census-state", type=Path, required=True)
    parser.add_argument("--previous-text-state", type=Path, required=True)
    parser.add_argument("--previous-move-state", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--additional-text-limit", type=int, default=10)
    parser.add_argument(
        "--selection-seed", default="corel-final-gate-additional-text-v1"
    )
    parser.add_argument("--timeout-seconds", type=float, default=240.0)
    parser.add_argument("--read-only-source", action="store_true", required=True)
    args = parser.parse_args()
    if not 0 <= args.additional_text_limit <= 20:
        raise ValueError("additional text limit must stay in 0..20")

    archive_root = args.archive_root.resolve()
    workspace = args.workspace.resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    inventory_rows = ArchiveDatabase(args.inventory).rows("cdr_candidate=1")
    inventory_by_id = {str(row["file_id"]): row for row in inventory_rows}
    rows_by_token = {
        source_token(Path(str(row["absolute_path"])), archive_root): row
        for row in inventory_rows
    }

    previous_text = [
        row["result"]
        for row in OperatorStateDatabase(args.previous_text_state).batch_rows(
            "real-mutation-pilot-001"
        )
    ]
    previous_move = [
        row["result"]
        for row in OperatorStateDatabase(args.previous_move_state).batch_rows(
            "real-mutation-pilot-001"
        )
    ]
    text_refused = [item for item in previous_text if item.get("result") == "UNSUPPORTED"]
    move_failed = [item for item in previous_move if item.get("result") == "FAILED"]
    if len(text_refused) != 14 or len(move_failed) != 2:
        raise ValueError("previous blocker cohort does not match the verified 14/2 baseline")

    text_refused_rows = [rows_by_token[str(item["source_token"])] for item in text_refused]
    move_failed_rows = [rows_by_token[str(item["source_token"])] for item in move_failed]
    previous_text_tokens = {str(item["source_token"]) for item in previous_text}
    excluded_file_ids = {
        str(row["file_id"])
        for token, row in rows_by_token.items()
        if token in previous_text_tokens
    }
    additional_rows = select_additional_text_rows(
        OperatorStateDatabase(args.census_state).census_rows(),
        inventory_by_id,
        excluded_file_ids=excluded_file_ids,
        limit=args.additional_text_limit,
        seed=args.selection_seed,
    )

    text_rerun = _run(
        text_refused_rows,
        archive_root=archive_root,
        workspace=workspace / "text_refused_rerun",
        mode="replace",
        timeout_seconds=args.timeout_seconds,
    )
    additional_text = _run(
        additional_rows,
        archive_root=archive_root,
        workspace=workspace / "text_additional",
        mode="replace",
        timeout_seconds=args.timeout_seconds,
    )
    move_rerun = _run(
        move_failed_rows,
        archive_root=archive_root,
        workspace=workspace / "move_failed_rerun",
        mode="move",
        timeout_seconds=args.timeout_seconds,
    )

    final_text = replace_prior_results(previous_text, text_rerun) + additional_text
    final_move = replace_prior_results(previous_move, move_rerun)
    summary = {
        "schema_version": "1.0",
        "planner_is_ai": False,
        "selection_seed": args.selection_seed,
        "targeted_real_cases": {
            "text_refused_rerun": len(text_refused_rows),
            "move_failed_rerun": len(move_failed_rows),
            "additional_text": len(additional_rows),
        },
        "new_source_mutations": sum(
            not bool(item.get("source_unchanged"))
            for item in text_rerun + additional_text + move_rerun
        ),
        "text_replace": summarize_family(final_text),
        "move": summarize_family(final_move),
        "rerun_outcomes": {
            "text_refused": summarize_family(text_rerun),
            "text_additional": summarize_family(additional_text),
            "move_failed": summarize_family(move_rerun),
        },
    }
    (workspace / "final_gate_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    return 0 if summary["new_source_mutations"] == 0 else 3


if __name__ == "__main__":
    raise SystemExit(main())
