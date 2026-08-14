from __future__ import annotations

import csv
from pathlib import Path

from PIL import Image

from training.tools.process_company_review_batches import (
    audit_private_batch,
    canonical_file_ids,
    initial_state,
    reset_missing_batch_previews,
    write_private_batch_files,
)


def test_initial_state_preserves_batch_one_ids_and_assigns_stable_new_ids() -> None:
    rows = [{"file_id": "file:a"}, {"file_id": "file:b"}, {"file_id": "file:c"}]
    state = initial_state(rows, {"file:b": "CDR_000001"})

    assert state["records"]["file:b"]["status"] == "REVIEW_PUBLISHED"
    assert state["records"]["file:b"]["batch"] == "batch_001"
    assert state["records"]["file:a"]["design_id"] == "CDR_000101"
    assert state["records"]["file:c"]["design_id"] == "CDR_000102"


def test_canonical_file_ids_keeps_first_duplicate_by_relative_path() -> None:
    rows = [
        {"file_id": "file:z", "relative_path": "z.cdr", "duplicate_group_id": "dup"},
        {"file_id": "file:a", "relative_path": "a.cdr", "duplicate_group_id": "dup"},
        {"file_id": "file:u", "relative_path": "unique.cdr", "duplicate_group_id": None},
    ]

    assert canonical_file_ids(rows) == {"file:a", "file:u"}


def test_private_batch_contains_only_sanitized_review_artifacts(tmp_path: Path) -> None:
    source_sheets: list[Path] = []
    for number in range(1, 3):
        sheet = tmp_path / f"contact_sheet_{number:03d}.jpg"
        Image.new("RGB", (100, 80), "white").save(sheet)
        source_sheets.append(sheet)
    rows = [
        {
            "design_id": f"CDR_{number:06d}",
            "contact_sheet": f"contact_sheet_{((number - 1) // 25) + 1:03d}.jpg",
            "sheet_position": ((number - 1) % 25) + 1,
            "source_token": f"CDR_{number:06d}",
        }
        for number in range(1, 27)
    ]
    target = tmp_path / "private" / "company_archive" / "batch_002"

    write_private_batch_files(
        target,
        batch_number=2,
        manifest_rows=rows,
        sheets=source_sheets,
    )
    audit_private_batch(target, 26)

    assert not (target / "previews").exists()
    with (target / "manifest_review.csv").open(
        "r", encoding="utf-8-sig", newline=""
    ) as handle:
        exported = list(csv.DictReader(handle))
    assert len(exported) == 26
    assert set(exported[0]) == {
        "design_id",
        "contact_sheet",
        "sheet_position",
        "source_token",
        "render_status",
    }


def test_resume_resets_success_when_local_preview_is_missing(tmp_path: Path) -> None:
    state = {
        "records": {
            "file:a": {
                "design_id": "CDR_000101",
                "status": "PREVIEW_SUCCESS",
                "batch": "batch_002",
                "error": None,
            }
        }
    }

    reset_missing_batch_previews(state, tmp_path, 2)

    assert state["records"]["file:a"]["status"] == "UNPROCESSED"
    assert state["records"]["file:a"]["batch"] is None
