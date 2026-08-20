from __future__ import annotations

from pathlib import Path

from PIL import Image

from training.corel_operator.artifacts import (
    build_mutation_review_artifacts,
    validate_private_artifact,
)


def test_mutation_review_artifact_is_sanitized(tmp_path: Path) -> None:
    workspace = tmp_path / "pilot"
    output = tmp_path / "private"
    workspace.mkdir()
    before = workspace / "before.png"
    after = workspace / "after.png"
    Image.new("RGB", (300, 200), "red").save(before)
    Image.new("RGB", (300, 200), "blue").save(after)
    rows = [
        {
            "result": {
                "result": "AUTO_SUCCESS",
                "source_token": "source:abc",
                "preview_before": str(before),
                "preview_after": str(after),
                "object_count_before": 3,
                "object_count_after": 3,
                "editability_verified": True,
                "source_unchanged": True,
            }
        }
    ]
    summary = build_mutation_review_artifacts(
        pilot_workspace=workspace,
        output_root=output,
        state_rows=rows,
    )
    assert summary["comparison_count"] == 1
    assert (output / "comparisons" / "OP_0001.jpg").is_file()
    assert (output / "contact_sheets" / "contact_sheet_001.jpg").is_file()
    validation = validate_private_artifact(output)
    assert validation["forbidden_binary_count"] == 0
    assert validation["path_leak_count"] == 0


def test_artifact_rejects_preview_outside_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "pilot"
    output = tmp_path / "private"
    workspace.mkdir()
    outside = tmp_path / "outside.png"
    Image.new("RGB", (10, 10), "white").save(outside)
    rows = [
        {
            "result": {
                "result": "AUTO_SUCCESS",
                "source_token": "source:abc",
                "preview_before": str(outside),
                "preview_after": str(outside),
            }
        }
    ]
    import pytest

    with pytest.raises(ValueError, match="escapes"):
        build_mutation_review_artifacts(
            pilot_workspace=workspace,
            output_root=output,
            state_rows=rows,
        )
