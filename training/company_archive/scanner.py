"""Resumable metadata-first scanner for an immutable company archive."""

from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path

from training.company_archive.classify import classify_extension
from training.company_archive.database import ArchiveDatabase
from training.company_archive.models import ArchiveFileRecord, ScanSummary
from training.company_archive.safety import resolve_archive_paths


def stable_file_id(relative_path: str) -> str:
    digest = hashlib.sha256(relative_path.casefold().encode("utf-8")).hexdigest()[:32]
    return f"file:{digest}"


def iter_archive_files(root: Path):
    """Yield deterministic paths without following directory symlinks."""

    for current, directories, files in os.walk(root, followlinks=False):
        directories[:] = sorted(
            name for name in directories if not (Path(current) / name).is_symlink()
        )
        for name in sorted(files):
            path = Path(current) / name
            if path.is_symlink():
                continue
            yield path


class ArchiveScanner:
    def __init__(self, root: Path, workspace: Path) -> None:
        self.root, self.workspace = resolve_archive_paths(root, workspace)
        self.database = ArchiveDatabase(self.workspace / "archive.sqlite")

    def scan(self, *, limit: int | None = None, resume: bool = True) -> ScanSummary:
        root_key = str(self.root)
        previous = self.database.get_scan_state(root_key) if resume else None
        cursor = previous.get("cursor_relative_path") if previous and not previous["completed"] else None
        resumed = bool(cursor)
        scan_id = previous["scan_id"] if resumed else time.strftime("scan-%Y%m%d-%H%M%S")
        scanned = 0
        skipped = 0
        last_path: str | None = cursor
        completed = True
        cursor_reached = cursor is None

        for path in iter_archive_files(self.root):
            relative = path.relative_to(self.root).as_posix()
            if not cursor_reached:
                skipped += 1
                if relative == cursor:
                    cursor_reached = True
                continue
            if limit is not None and scanned >= limit:
                completed = False
                break
            try:
                stat = path.stat()
                file_type, cdr, pdf, image = classify_extension(path.suffix)
                record = ArchiveFileRecord(
                    file_id=stable_file_id(relative),
                    absolute_path=str(path.resolve()),
                    relative_path=relative,
                    filename=path.name,
                    extension=path.suffix.casefold(),
                    size_bytes=stat.st_size,
                    modified_time=stat.st_mtime,
                    created_time=getattr(stat, "st_ctime", None),
                    file_type=file_type,
                    cdr_candidate=cdr,
                    pdf_candidate=pdf,
                    image_candidate=image,
                )
                self.database.upsert_file(record, scan_id=scan_id)
                scanned += 1
                last_path = relative
                if scanned % 250 == 0:
                    self.database.set_scan_state(root_key, scan_id, last_path, False)
            except (OSError, ValueError):
                # A disappearing/unreadable file is retried on the next run; no
                # source mutation or invented metadata is recorded.
                continue

        if cursor is not None and not cursor_reached:
            # The prior cursor disappeared or the directory ordering changed.
            # Fail closed instead of incorrectly marking an incomplete scan done.
            raise RuntimeError(
                "resume cursor is no longer present; start an explicit fresh inventory scan"
            )

        self.database.set_scan_state(root_key, scan_id, last_path, completed)
        stats = self.database.statistics()
        return ScanSummary(
            root=root_key,
            workspace=str(self.workspace),
            scan_id=scan_id,
            resumed=resumed,
            completed=completed,
            scanned_files=scanned,
            skipped_before_cursor=skipped,
            **stats,
        )
