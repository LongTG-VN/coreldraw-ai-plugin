"""SQLite persistence for resumable inventory and human curation state."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from training.company_archive.models import ArchiveFileRecord


SCHEMA_VERSION = "1"


class ArchiveDatabase:
    def __init__(self, path: Path) -> None:
        self.path = path.resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS files (
                    file_id TEXT PRIMARY KEY,
                    absolute_path TEXT NOT NULL UNIQUE,
                    relative_path TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    extension TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    modified_time REAL NOT NULL,
                    created_time REAL,
                    fast_hash TEXT,
                    sha256_status TEXT NOT NULL,
                    sha256 TEXT,
                    file_type TEXT NOT NULL,
                    cdr_candidate INTEGER NOT NULL,
                    pdf_candidate INTEGER NOT NULL,
                    image_candidate INTEGER NOT NULL,
                    inventory_status TEXT NOT NULL,
                    preview_status TEXT NOT NULL,
                    corel_inspection_status TEXT NOT NULL,
                    duplicate_group_id TEXT,
                    duplicate_confidence TEXT,
                    category TEXT,
                    category_source TEXT,
                    human_quality_status TEXT NOT NULL,
                    gold_status TEXT NOT NULL,
                    rights_status TEXT NOT NULL,
                    commercial_allowed INTEGER NOT NULL,
                    human_reviewer TEXT,
                    notes TEXT,
                    preview_path TEXT,
                    preview_width INTEGER,
                    preview_height INTEGER,
                    render_error TEXT,
                    inspection_json TEXT,
                    last_seen_scan_id TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_files_fast_duplicate
                    ON files(size_bytes, fast_hash);
                CREATE INDEX IF NOT EXISTS idx_files_sha256 ON files(sha256);
                CREATE INDEX IF NOT EXISTS idx_files_curation
                    ON files(human_quality_status, gold_status);
                CREATE TABLE IF NOT EXISTS scan_state (
                    root TEXT PRIMARY KEY,
                    scan_id TEXT NOT NULL,
                    cursor_relative_path TEXT,
                    completed INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS curation_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_id TEXT NOT NULL,
                    reviewer TEXT NOT NULL,
                    human_quality_status TEXT NOT NULL,
                    gold_status TEXT NOT NULL,
                    category TEXT,
                    rights_status TEXT NOT NULL,
                    notes TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(file_id) REFERENCES files(file_id)
                );
                """
            )
            db.execute(
                "INSERT OR REPLACE INTO metadata(key,value) VALUES('schema_version',?)",
                (SCHEMA_VERSION,),
            )

    def upsert_file(self, record: ArchiveFileRecord, *, scan_id: str) -> None:
        payload = record.model_dump(mode="json")
        columns = list(payload) + ["last_seen_scan_id"]
        values = [payload[name] for name in payload] + [scan_id]
        values = [
            json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value
            for value in values
        ]
        assignments = ",".join(
            f"{column}=excluded.{column}"
            for column in columns
            if column not in {"file_id", "human_quality_status", "gold_status", "rights_status", "commercial_allowed", "human_reviewer", "notes"}
        )
        placeholders = ",".join("?" for _ in columns)
        with self.connect() as db:
            db.execute(
                f"INSERT INTO files({','.join(columns)}) VALUES({placeholders}) "
                f"ON CONFLICT(file_id) DO UPDATE SET {assignments},updated_at=CURRENT_TIMESTAMP",
                values,
            )

    def get_file(self, file_id: str) -> dict[str, Any]:
        with self.connect() as db:
            row = db.execute("SELECT * FROM files WHERE file_id=?", (file_id,)).fetchone()
        if row is None:
            raise KeyError(file_id)
        return dict(row)

    def rows(self, where: str = "1=1", params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        with self.connect() as db:
            values = db.execute(
                f"SELECT * FROM files WHERE {where} ORDER BY relative_path", params
            ).fetchall()
        return [dict(row) for row in values]

    def set_scan_state(self, root: str, scan_id: str, cursor: str | None, completed: bool) -> None:
        with self.connect() as db:
            db.execute(
                """INSERT INTO scan_state(root,scan_id,cursor_relative_path,completed)
                VALUES(?,?,?,?) ON CONFLICT(root) DO UPDATE SET
                scan_id=excluded.scan_id,cursor_relative_path=excluded.cursor_relative_path,
                completed=excluded.completed,updated_at=CURRENT_TIMESTAMP""",
                (root, scan_id, cursor, int(completed)),
            )

    def get_scan_state(self, root: str) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute("SELECT * FROM scan_state WHERE root=?", (root,)).fetchone()
        return dict(row) if row else None

    def update_fields(self, file_id: str, **fields: Any) -> None:
        allowed = {
            "fast_hash", "sha256_status", "sha256", "duplicate_group_id",
            "duplicate_confidence", "preview_status", "preview_path", "preview_width",
            "preview_height", "render_error", "corel_inspection_status", "inspection_json",
            "category", "category_source", "human_quality_status", "gold_status",
            "rights_status", "commercial_allowed", "human_reviewer", "notes",
        }
        if not fields or not set(fields) <= allowed:
            raise ValueError("invalid inventory update fields")
        assignments = ",".join(f"{name}=?" for name in fields)
        values = [getattr(value, "value", value) for value in fields.values()]
        with self.connect() as db:
            cursor = db.execute(
                f"UPDATE files SET {assignments},updated_at=CURRENT_TIMESTAMP WHERE file_id=?",
                (*values, file_id),
            )
            if cursor.rowcount != 1:
                raise KeyError(file_id)

    def statistics(self) -> dict[str, Any]:
        with self.connect() as db:
            totals = db.execute(
                """SELECT COUNT(*) total_files,COALESCE(SUM(size_bytes),0) total_bytes,
                SUM(cdr_candidate) cdr_count,
                COALESCE(SUM(CASE WHEN cdr_candidate=1 THEN size_bytes ELSE 0 END),0) cdr_total_size,
                SUM(pdf_candidate) pdf_count,SUM(image_candidate) image_count,
                SUM(CASE WHEN cdr_candidate=0 AND pdf_candidate=0 AND image_candidate=0 THEN 1 ELSE 0 END) other_count,
                MIN(modified_time) oldest_modified_time,MAX(modified_time) newest_modified_time
                FROM files"""
            ).fetchone()
            largest = db.execute(
                "SELECT file_id,relative_path,size_bytes FROM files ORDER BY size_bytes DESC LIMIT 20"
            ).fetchall()
        result = dict(totals)
        result["largest_files"] = [dict(row) for row in largest]
        return result

