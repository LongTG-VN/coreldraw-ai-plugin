"""Run deterministic real-CDR transaction rollback controls on working copies."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from training.company_archive.database import ArchiveDatabase
from training.company_archive.safety import assert_source_unchanged, source_stat_guard
from training.corel_operator.policy import sanitize_error, source_token
from training.corel_operator.rollback import verify_real_transaction_rollback
from training.corel_operator.state import OperatorStateDatabase


def select_rollback_control_rows(
    census_rows: list[dict[str, Any]],
    inventory_by_file_id: dict[str, dict[str, Any]],
    *,
    limit: int,
    seed: str,
) -> list[dict[str, Any]]:
    if limit < 1:
        raise ValueError("rollback control limit must be positive")
    eligible: list[dict[str, Any]] = []
    for state_row in census_rows:
        result = state_row["result"]
        counts = result.get("counts", {})
        row = inventory_by_file_id.get(str(state_row["file_id"]))
        if (
            row is not None
            and bool(result.get("operator_eligible"))
            and int(counts.get("text", 0)) > 0
            and int(counts.get("objects", 0)) > int(counts.get("pasteboard", 0))
        ):
            eligible.append(row)
    return sorted(
        eligible,
        key=lambda row: hashlib.sha256(
            f"{seed}:{row['file_id']}".encode("utf-8")
        ).hexdigest(),
    )[:limit]


def summarize_rollback_controls(
    payloads: list[dict[str, Any]], *, expected_count: int, selection_seed: str
) -> dict[str, Any]:
    counts = Counter(str(item.get("status")) for item in payloads)
    return {
        "schema_version": "1.0",
        "planner_is_ai": False,
        "expected_count": expected_count,
        "attempted": len(payloads),
        "verified": counts["VERIFIED"],
        "unsupported": counts["UNSUPPORTED"],
        "failed": counts["FAILED"],
        "source_mutations": sum(
            not bool(item.get("source_unchanged")) for item in payloads
        ),
        "selection_seed": selection_seed,
        "results": payloads,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive-root", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--census-state", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--selection-seed", default="corel-rollback-controls-v1")
    parser.add_argument("--read-only-source", action="store_true", required=True)
    args = parser.parse_args()

    archive_root = args.archive_root.resolve()
    workspace = args.workspace.resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    inventory_rows = ArchiveDatabase(args.inventory).rows("cdr_candidate=1")
    inventory_by_id = {str(row["file_id"]): row for row in inventory_rows}
    rows = select_rollback_control_rows(
        OperatorStateDatabase(args.census_state).census_rows(),
        inventory_by_id,
        limit=args.limit,
        seed=args.selection_seed,
    )
    payloads: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        source = Path(str(row["absolute_path"])).resolve()
        token = source_token(source, archive_root)
        guard = source_stat_guard(source)
        try:
            result = verify_real_transaction_rollback(
                source_path=source,
                archive_root=archive_root,
                workspace=workspace / "controls",
            )
        except Exception as exc:
            result = {
                "source_token": token,
                "status": "FAILED",
                "error": sanitize_error(exc, archive_root=archive_root),
                "source_unchanged": True,
            }
        # A source mutation is an immediate fatal condition, not an ordinary
        # failed control that the batch may continue past.
        assert_source_unchanged(source, guard)
        result["source_unchanged"] = True
        payloads.append(result)
        print(f"[{index}/{len(rows)}] {token} {result['status']}", flush=True)

    summary = summarize_rollback_controls(
        payloads,
        expected_count=args.limit,
        selection_seed=args.selection_seed,
    )
    (workspace / "rollback_control_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    complete = (
        summary["attempted"] == args.limit
        and summary["verified"] == args.limit
        and summary["source_mutations"] == 0
    )
    return 0 if complete else 2


if __name__ == "__main__":
    raise SystemExit(main())
