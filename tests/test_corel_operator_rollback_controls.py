from training.tools.run_corel_operator_rollback_controls import (
    select_rollback_control_rows,
    summarize_rollback_controls,
)


def test_rollback_control_selection_is_deterministic_and_page_eligible() -> None:
    inventory = {
        "a": {"file_id": "a"},
        "b": {"file_id": "b"},
        "c": {"file_id": "c"},
    }
    census = [
        {
            "file_id": "a",
            "result": {
                "operator_eligible": True,
                "counts": {"text": 1, "objects": 2, "pasteboard": 0},
            },
        },
        {
            "file_id": "b",
            "result": {
                "operator_eligible": True,
                "counts": {"text": 0, "objects": 2, "pasteboard": 0},
            },
        },
        {
            "file_id": "c",
            "result": {
                "operator_eligible": True,
                "counts": {"text": 2, "objects": 2, "pasteboard": 2},
            },
        },
    ]
    first = select_rollback_control_rows(census, inventory, limit=2, seed="fixed")
    second = select_rollback_control_rows(census, inventory, limit=2, seed="fixed")
    assert first == second == [inventory["a"]]


def test_rollback_control_summary_preserves_failures_and_source_safety() -> None:
    summary = summarize_rollback_controls(
        [
            {"status": "VERIFIED", "source_unchanged": True},
            {"status": "UNSUPPORTED", "source_unchanged": True},
            {"status": "FAILED", "source_unchanged": False},
        ],
        expected_count=3,
        selection_seed="fixed",
    )
    assert summary["attempted"] == 3
    assert summary["verified"] == 1
    assert summary["unsupported"] == 1
    assert summary["failed"] == 1
    assert summary["source_mutations"] == 1
