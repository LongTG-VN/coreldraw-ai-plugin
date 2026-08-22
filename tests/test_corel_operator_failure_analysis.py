from training.corel_operator.failure_analysis import (
    build_failure_analysis,
    classify_operator_failure,
)


def test_failure_classifier_keeps_narrow_root_causes() -> None:
    assert classify_operator_failure({"error": "TextRange unexpected error"})[0] == (
        "TEXT_RANGE_COM"
    )
    assert classify_operator_failure(
        {"error": "object one changed outside policy: bbox"}
    )[0] == "COLLATERAL_BBOX_POLICY"
    assert classify_operator_failure({"error_code": "WORKER_FAILURE"})[0] == (
        "WORKER_RUNTIME"
    )


def test_failure_report_is_sanitized_and_does_not_invent_reproduction() -> None:
    report = build_failure_analysis(
        [
            {
                "result": "FAILED",
                "source_token": "source:abc",
                "error": "TextRange unexpected error",
                "error_code": "COREL_RUNTIME_FAILURE",
                "source_unchanged": True,
                "rollback_verified": True,
                "attempt": 2,
            },
            {"result": "AUTO_SUCCESS", "source_token": "source:ok"},
        ]
    )
    assert report["failure_count"] == 1
    assert report["categories"] == {"TEXT_RANGE_COM": 1}
    assert report["records"][0]["reproducible"] is None
    assert report["records"][0]["source_unchanged"] is True
    assert report["contains_private_paths"] is False
