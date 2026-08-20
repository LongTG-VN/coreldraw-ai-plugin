"""Crash-safe SQLite state for long-running operator census and batch work."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


class OperatorStateDatabase:
    def __init__(self, path: Path) -> None:
        self.path = path.expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS census_results (
                    source_token TEXT PRIMARY KEY,
                    file_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS batch_results (
                    run_id TEXT NOT NULL,
                    source_token TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempt_count INTEGER NOT NULL DEFAULT 1,
                    result_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY(run_id, source_token)
                );
                """
            )

    def put_census(self, source_token: str, file_id: str, status: str, result: dict[str, Any]) -> None:
        with self.connect() as db:
            db.execute(
                """INSERT INTO census_results(source_token,file_id,status,result_json)
                VALUES(?,?,?,?) ON CONFLICT(source_token) DO UPDATE SET
                status=excluded.status,result_json=excluded.result_json,
                updated_at=CURRENT_TIMESTAMP""",
                (source_token, file_id, status, json.dumps(result, ensure_ascii=False)),
            )

    def census_tokens(self, *, statuses: tuple[str, ...] = ("COMPLETE",)) -> set[str]:
        placeholders = ",".join("?" for _ in statuses)
        with self.connect() as db:
            rows = db.execute(
                f"SELECT source_token FROM census_results WHERE status IN ({placeholders})",
                statuses,
            ).fetchall()
        return {str(row[0]) for row in rows}

    def census_rows(self) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT * FROM census_results ORDER BY source_token"
            ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["result"] = json.loads(item.pop("result_json"))
            result.append(item)
        return result

    def put_batch(
        self,
        run_id: str,
        source_token: str,
        status: str,
        result: dict[str, Any],
        *,
        attempt_count: int = 1,
    ) -> None:
        with self.connect() as db:
            db.execute(
                """INSERT INTO batch_results(run_id,source_token,status,attempt_count,result_json)
                VALUES(?,?,?,?,?) ON CONFLICT(run_id,source_token) DO UPDATE SET
                status=excluded.status,attempt_count=excluded.attempt_count,
                result_json=excluded.result_json,updated_at=CURRENT_TIMESTAMP""",
                (
                    run_id,
                    source_token,
                    status,
                    attempt_count,
                    json.dumps(result, ensure_ascii=False),
                ),
            )

    def batch_rows(self, run_id: str) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT * FROM batch_results WHERE run_id=? ORDER BY source_token",
                (run_id,),
            ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["result"] = json.loads(item.pop("result_json"))
            result.append(item)
        return result
