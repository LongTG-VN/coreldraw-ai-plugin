from training.corel_operator.ambiguity import (
    build_ambiguous_text_control_plan,
    summarize_ambiguity_controls,
)


def test_ambiguous_control_requires_unique_all_text_selector() -> None:
    plan = build_ambiguous_text_control_plan(control_id="001")

    assert plan.metadata["ambiguous_control"] is True
    assert plan.metadata["planner_is_ai"] is False
    assert plan.actions[0].target.kind.value == "regex_text"
    assert plan.actions[0].target.value == ".*"
    assert plan.actions[0].target.require_unique is True


def test_ambiguity_summary_counts_only_fail_closed_human_review() -> None:
    summary = summarize_ambiguity_controls(
        [
            {
                "result": "NEEDS_REVIEW",
                "error_code": "TARGET_NOT_UNIQUE_OR_MISSING",
                "transaction_committed": False,
                "source_unchanged": True,
            },
            {
                "result": "AUTO_SUCCESS",
                "transaction_committed": True,
                "source_unchanged": True,
            },
        ]
    )

    assert summary["control_cases"] == 2
    assert summary["safely_refused"] == 1
    assert summary["unexpected_results"] == 1
    assert summary["source_mutations"] == 0
