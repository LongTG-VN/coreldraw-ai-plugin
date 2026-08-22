from __future__ import annotations

from training.tools.run_corel_operator_targeted_pilot import summarize_targeted


def test_targeted_summary_preserves_all_terminal_classes() -> None:
    payloads = [
        {
            "result": "AUTO_SUCCESS",
            "source_unchanged": True,
            "editability_verified": True,
            "elapsed_seconds": 2.0,
        },
        {
            "result": "NEEDS_REVIEW",
            "source_unchanged": True,
            "editability_verified": True,
            "elapsed_seconds": 4.0,
        },
        {
            "result": "UNSUPPORTED",
            "source_unchanged": True,
            "editability_verified": False,
            "elapsed_seconds": 1.0,
        },
        {
            "result": "FAILED",
            "source_unchanged": True,
            "editability_verified": False,
            "elapsed_seconds": 3.0,
        },
    ]

    summary = summarize_targeted(payloads, mode="replace", seed="fixture")

    assert summary["attempted"] == 4
    assert summary["auto_success"] == 1
    assert summary["needs_review"] == 1
    assert summary["unsupported"] == 1
    assert summary["failed"] == 1
    assert summary["save_reopen_pass"] == 2
    assert summary["source_mutations"] == 0
    assert summary["median_seconds"] == 2.5
