"""Replay prior failed deterministic tasks through the hardened operator."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from training.company_archive.database import ArchiveDatabase
from training.corel_operator.models import OperatorResultClass
from training.corel_operator.policy import source_token
from training.corel_operator.reliability import classify_failure_replay
from training.corel_operator.state import OperatorStateDatabase
from training.tools.reevaluate_corel_visual_qa_v2 import (
    execute_previous_result_replay,
)


RUN_ID = "failure-replay-001"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive-root", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--previous-state", type=Path, required=True)
    parser.add_argument("--previous-run-id", default="real-mutation-pilot-001")
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=float, default=240)
    parser.add_argument("--max-attempts", type=int, default=2)
    parser.add_argument("--read-only-source", action="store_true", required=True)
    args = parser.parse_args()

    archive_root = args.archive_root.resolve()
    workspace = args.workspace.resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    state = OperatorStateDatabase(workspace / "failure_replay.sqlite")
    previous = OperatorStateDatabase(args.previous_state)
    failed_rows = [
        row["result"]
        for row in previous.batch_rows(args.previous_run_id)
        if row["result"].get("result") == OperatorResultClass.FAILED.value
    ]
    by_token = {str(item["source_token"]): item for item in failed_rows}
    source_rows = {
        source_token(Path(str(row["absolute_path"])), archive_root): row
        for row in ArchiveDatabase(args.inventory).rows("cdr_candidate=1")
    }
    completed = {row["source_token"] for row in state.batch_rows(RUN_ID)}
    for index, token in enumerate(sorted(by_token), start=1):
        if token in completed:
            print(f"[{index}/{len(by_token)}] {token} RESUME_SKIP", flush=True)
            continue
        row = source_rows.get(token)
        if row is None:
            result = {
                "result": OperatorResultClass.UNSUPPORTED.value,
                "source_token": token,
                "source_unchanged": True,
                "error_code": "SOURCE_MAPPING_MISSING",
                "attempt": 0,
            }
        else:
            result = {}
            for attempt in range(1, args.max_attempts + 1):
                result = execute_previous_result_replay(
                    row=row,
                    previous_result=by_token[token],
                    archive_root=archive_root,
                    workspace=workspace,
                    attempt=attempt,
                    timeout_seconds=args.timeout_seconds,
                )
                if result.get("result") != OperatorResultClass.FAILED.value:
                    break
        result["failure_replay_class"] = classify_failure_replay(result)
        state.put_batch(
            RUN_ID,
            token,
            str(result["failure_replay_class"]),
            result,
            attempt_count=int(result.get("attempt", 0)),
        )
        print(
            f"[{index}/{len(by_token)}] {token} {result['failure_replay_class']}",
            flush=True,
        )

    output = state.batch_rows(RUN_ID)
    classes = Counter(row["result"]["failure_replay_class"] for row in output)
    summary = {
        "run_id": RUN_ID,
        "expected_count": len(failed_rows),
        "processed_count": len(output),
        "fixed": classes["FIXED"],
        "needs_review": classes["NEEDS_REVIEW"],
        "failed": classes["FAILED"],
        "not_replayable": classes["NOT_REPLAYABLE"],
        "source_mutations": sum(
            not bool(row["result"].get("source_unchanged")) for row in output
        ),
    }
    (workspace / "failure_replay_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    return 0 if summary["processed_count"] == summary["expected_count"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
