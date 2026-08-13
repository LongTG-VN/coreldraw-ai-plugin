"""Staged duplicate grouping: size → fast fingerprint → SHA256 verification."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from pathlib import Path

from training.company_archive.database import ArchiveDatabase
from training.company_archive.hashing import fast_fingerprint, sha256_file
from training.company_archive.models import WorkStatus
from training.company_archive.safety import assert_source_unchanged, source_stat_guard


def fingerprint_candidates(database: ArchiveDatabase) -> int:
    groups: dict[int, list[dict]] = defaultdict(list)
    for row in database.rows():
        groups[int(row["size_bytes"])].append(row)
    updated = 0
    for rows in groups.values():
        if len(rows) < 2:
            continue
        for row in rows:
            path = Path(row["absolute_path"])
            before = source_stat_guard(path)
            digest = fast_fingerprint(path)
            assert_source_unchanged(path, before)
            database.update_fields(row["file_id"], fast_hash=digest)
            updated += 1
    return updated


def verify_duplicate_groups(database: ArchiveDatabase) -> int:
    candidates: dict[tuple[int, str], list[dict]] = defaultdict(list)
    for row in database.rows("fast_hash IS NOT NULL"):
        candidates[(int(row["size_bytes"]), str(row["fast_hash"]))].append(row)
    groups = 0
    for rows in candidates.values():
        if len(rows) < 2:
            continue
        by_sha: dict[str, list[dict]] = defaultdict(list)
        for row in rows:
            path = Path(row["absolute_path"])
            before = source_stat_guard(path)
            digest = sha256_file(path)
            assert_source_unchanged(path, before)
            database.update_fields(
                row["file_id"], sha256=digest, sha256_status=WorkStatus.COMPLETE
            )
            by_sha[digest].append(row)
        for digest, verified in by_sha.items():
            if len(verified) < 2:
                continue
            group_id = "duplicate:" + hashlib.sha256(digest.encode()).hexdigest()[:20]
            for row in verified:
                database.update_fields(
                    row["file_id"],
                    duplicate_group_id=group_id,
                    duplicate_confidence="SHA256_VERIFIED",
                )
            groups += 1
    return groups


def bind_full_sha256(database: ArchiveDatabase, file_id: str) -> str:
    row = database.get_file(file_id)
    path = Path(row["absolute_path"])
    before = source_stat_guard(path)
    digest = sha256_file(path)
    assert_source_unchanged(path, before)
    database.update_fields(file_id, sha256=digest, sha256_status=WorkStatus.COMPLETE)
    return digest

