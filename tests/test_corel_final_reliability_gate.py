from training.tools.run_corel_final_reliability_gate import (
    replace_prior_results,
    select_additional_text_rows,
    summarize_family,
)


def test_additional_text_selection_excludes_previous_fixed_sample() -> None:
    inventory = {
        f"file-{index}": {"file_id": f"file-{index}"}
        for index in range(5)
    }
    census = [
        {
            "file_id": f"file-{index}",
            "result": {
                "operator_eligible": True,
                "counts": {"objects": 2, "pasteboard": 0, "text": index % 2},
            },
        }
        for index in range(5)
    ]

    selected = select_additional_text_rows(
        census,
        inventory,
        excluded_file_ids={"file-1"},
        limit=10,
        seed="fixed",
    )

    assert selected == [inventory["file-3"]]


def test_rerun_replaces_prior_result_without_double_counting() -> None:
    previous = [
        {"source_token": "source:a", "result": "UNSUPPORTED"},
        {"source_token": "source:b", "result": "AUTO_SUCCESS"},
    ]
    rerun = [
        {
            "source_token": "source:a",
            "result": "AUTO_SUCCESS",
            "source_unchanged": True,
            "editability_verified": True,
        }
    ]

    combined = replace_prior_results(previous, rerun)
    summary = summarize_family(combined)

    assert len(combined) == 2
    assert summary["auto_success"] == 2
    assert summary["unsupported"] == 0


def test_family_summary_keeps_failures_and_review_separate() -> None:
    summary = summarize_family(
        [
            {
                "result": "AUTO_SUCCESS",
                "source_unchanged": True,
                "editability_verified": True,
            },
            {
                "result": "NEEDS_REVIEW",
                "source_unchanged": True,
                "editability_verified": True,
            },
            {
                "result": "FAILED",
                "source_unchanged": True,
                "editability_verified": False,
            },
        ]
    )

    assert summary["executed"] == 2
    assert summary["failed"] == 1
    assert summary["save_reopen_pass_rate"] == 1.0
    assert summary["failed_rate"] == 1 / 3
