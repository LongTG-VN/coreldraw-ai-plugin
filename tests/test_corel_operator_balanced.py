from __future__ import annotations

from training.corel_operator.balanced import (
    BALANCED_OPERATION_MODES,
    select_balanced_rows,
    summarize_balanced_results,
)


def test_balanced_selection_is_deterministic_and_excludes_pasteboard_only_rows() -> None:
    inventory = {
        f"file-{index}": {"file_id": f"file-{index}", "absolute_path": f"{index}.cdr"}
        for index in range(8)
    }
    census = [
        {
            "file_id": f"file-{index}",
            "result": {
                "operator_eligible": True,
                "counts": {
                    "objects": 5,
                    "pasteboard": 5 if index == 7 else index % 2,
                },
            },
        }
        for index in range(8)
    ]
    first = select_balanced_rows(census, inventory, limit_per_mode=4, seed="seed")
    second = select_balanced_rows(census, inventory, limit_per_mode=4, seed="seed")
    assert first == second
    assert set(first) == set(BALANCED_OPERATION_MODES)
    assert all(len(rows) == 4 for rows in first.values())
    assert all(row["file_id"] != "file-7" for rows in first.values() for row in rows)
    # The fixture has only seven eligible files, so reuse occurs only after
    # fresh files are exhausted.
    assert len({row["file_id"] for rows in first.values() for row in rows}) == 7


def test_balanced_summary_keeps_unsupported_and_failure_separate() -> None:
    payloads = {
        mode: [
            {
                "source_token": f"source:{mode}:success",
                "result": "AUTO_SUCCESS",
                "transaction_committed": True,
                "editability_verified": True,
                "source_unchanged": True,
                "elapsed_seconds": 2.0,
            },
            {
                "source_token": f"source:{mode}:unsupported",
                "result": "UNSUPPORTED",
                "transaction_committed": False,
                "editability_verified": False,
                "source_unchanged": True,
                "elapsed_seconds": 1.0,
            },
        ]
        for mode in BALANCED_OPERATION_MODES
    }
    payloads["move"].append(
        {
            "source_token": "source:move:failed",
            "result": "FAILED",
            "transaction_committed": False,
            "editability_verified": False,
            "source_unchanged": True,
            "elapsed_seconds": 3.0,
        }
    )
    summary = summarize_balanced_results(
        payloads,
        expected_per_mode={mode: len(payloads[mode]) for mode in BALANCED_OPERATION_MODES},
        selection_seed="seed",
    )
    assert summary["tasks_total"] == 9
    assert summary["auto_success"] == 4
    assert summary["unsupported"] == 4
    assert summary["failed"] == 1
    assert summary["executed"] == summary["save_reopen_pass"] == 4
    assert summary["source_mutations"] == 0
