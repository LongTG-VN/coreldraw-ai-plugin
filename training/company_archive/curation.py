"""Human-only archive curation with immutable append-only event records."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from training.company_archive.database import ArchiveDatabase
from training.company_archive.duplicates import bind_full_sha256
from training.company_archive.models import (
    ArchiveCategory,
    ArchiveFileRecord,
    GoldStatus,
    HumanQualityStatus,
    RightsStatus,
)


def curate_file(
    database: ArchiveDatabase,
    *,
    file_id: str,
    reviewer: str,
    quality: HumanQualityStatus,
    category: ArchiveCategory | None = None,
    gold_status: GoldStatus = GoldStatus.NOT_GOLD,
    rights_status: RightsStatus = RightsStatus.UNKNOWN,
    commercial_allowed: bool = False,
    notes: str | None = None,
    source: str = "human_ui_action",
) -> ArchiveFileRecord:
    if source != "human_ui_action":
        raise ValueError("only explicit human UI actions may curate company Gold")
    reviewer = reviewer.strip()
    if not reviewer:
        raise ValueError("reviewer is required")
    current = database.get_file(file_id)
    if gold_status == GoldStatus.HUMAN_CERTIFIED_GOLD and not current.get("sha256"):
        bind_full_sha256(database, file_id)
        current = database.get_file(file_id)

    payload = {
        key: current[key]
        for key in ArchiveFileRecord.model_fields
        if key in current
    }
    payload.update(
        {
            "human_quality_status": quality,
            "category": category,
            "category_source": "human",
            "gold_status": gold_status,
            "rights_status": rights_status,
            "commercial_allowed": commercial_allowed,
            "human_reviewer": reviewer,
            "notes": notes,
        }
    )
    validated = ArchiveFileRecord.model_validate(payload)
    database.update_fields(
        file_id,
        human_quality_status=quality,
        category=category,
        category_source="human",
        gold_status=gold_status,
        rights_status=rights_status,
        commercial_allowed=commercial_allowed,
        human_reviewer=reviewer,
        notes=notes,
    )
    with database.connect() as db:
        db.execute(
            """INSERT INTO curation_events(
            file_id,reviewer,human_quality_status,gold_status,category,
            rights_status,notes,created_at) VALUES(?,?,?,?,?,?,?,?)""",
            (
                file_id,
                reviewer,
                quality.value,
                gold_status.value,
                category.value if category else None,
                rights_status.value,
                notes,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
    return ArchiveFileRecord.model_validate(
        {key: database.get_file(file_id)[key] for key in ArchiveFileRecord.model_fields}
    )

