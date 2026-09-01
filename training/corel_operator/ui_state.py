"""Persistent local state and bounded desktop helpers for the Corel UI V1."""

from __future__ import annotations

import json
import os
import re
import shutil
import socket
import sqlite3
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal

from PIL import Image
from pydantic import Field, field_validator

from training.corel_operator.models import StrictModel


_TASK_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$")
_OUTPUT_SUBFOLDER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_/-]{0,95}$")


class UiSettingsV1(StrictModel):
    output_subfolder: str = "jobs"
    default_pdf_export: bool = True
    default_png_export: bool = True
    preview_quality: Literal["standard", "high"] = "high"
    recent_job_limit: int = Field(default=20, ge=5, le=100)

    @field_validator("output_subfolder")
    @classmethod
    def safe_output_subfolder(cls, value: str) -> str:
        normalized = value.replace("\\", "/").strip("/")
        if (
            not _OUTPUT_SUBFOLDER_RE.fullmatch(normalized)
            or ".." in normalized.split("/")
        ):
            raise ValueError("output folder must be a safe workspace-relative path")
        return normalized


class UiJobRecordV1(StrictModel):
    task_id: str = Field(pattern=_TASK_ID_RE.pattern)
    file_id: str
    instruction: str = Field(min_length=1, max_length=2000)
    kind: Literal["MUTATION", "EXPORT_ONLY"] = "MUTATION"
    status: str
    qa_status: str = "WAITING"
    message: str = ""
    source_unchanged: bool | None = None
    rollback_verified: bool = False
    output_version: int | None = Field(default=None, ge=1, le=9999)
    outputs: dict[str, str] = Field(default_factory=dict)
    diagnostic: dict[str, Any] | None = None
    created_at: str
    updated_at: str


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class UiSettingsStore:
    def __init__(self, path: Path) -> None:
        self.path = path.resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> UiSettingsV1:
        if not self.path.is_file():
            return UiSettingsV1()
        return UiSettingsV1.model_validate_json(self.path.read_text(encoding="utf-8"))

    def save(self, settings: UiSettingsV1) -> UiSettingsV1:
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(settings.model_dump_json(indent=2), encoding="utf-8")
        temporary.replace(self.path)
        return settings


class UiJobStore:
    def __init__(self, path: Path) -> None:
        self.path = path.resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as database:
            database.execute(
                """CREATE TABLE IF NOT EXISTS ui_jobs (
                task_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                payload_json TEXT NOT NULL
                )"""
            )

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def put(self, record: UiJobRecordV1) -> UiJobRecordV1:
        with self.connect() as database:
            database.execute(
                """INSERT INTO ui_jobs(task_id,status,created_at,updated_at,payload_json)
                VALUES(?,?,?,?,?) ON CONFLICT(task_id) DO UPDATE SET
                status=excluded.status,updated_at=excluded.updated_at,
                payload_json=excluded.payload_json""",
                (
                    record.task_id,
                    record.status,
                    record.created_at,
                    record.updated_at,
                    record.model_dump_json(),
                ),
            )
        return record

    def create(
        self,
        *,
        task_id: str,
        file_id: str,
        instruction: str,
        kind: Literal["MUTATION", "EXPORT_ONLY"],
        status: str,
        message: str,
    ) -> UiJobRecordV1:
        timestamp = _now()
        return self.put(
            UiJobRecordV1(
                task_id=task_id,
                file_id=file_id,
                instruction=instruction,
                kind=kind,
                status=status,
                message=message,
                created_at=timestamp,
                updated_at=timestamp,
            )
        )

    def get(self, task_id: str) -> UiJobRecordV1:
        if not _TASK_ID_RE.fullmatch(task_id):
            raise KeyError(task_id)
        with self.connect() as database:
            row = database.execute(
                "SELECT payload_json FROM ui_jobs WHERE task_id=?", (task_id,)
            ).fetchone()
        if row is None:
            raise KeyError(task_id)
        return UiJobRecordV1.model_validate_json(str(row[0]))

    def list_recent(self, limit: int) -> list[UiJobRecordV1]:
        bounded = max(1, min(int(limit), 100))
        with self.connect() as database:
            rows = database.execute(
                "SELECT payload_json FROM ui_jobs ORDER BY updated_at DESC LIMIT ?",
                (bounded,),
            ).fetchall()
        return [UiJobRecordV1.model_validate_json(str(row[0])) for row in rows]

    def update(self, task_id: str, **changes: Any) -> UiJobRecordV1:
        current = self.get(task_id)
        changes["updated_at"] = _now()
        return self.put(current.model_copy(update=changes))


class UiOutputManager:
    _SOURCE_NAMES = {
        "cdr": "working_copy.cdr",
        "pdf": "working_copy.pdf",
        "png": "working_copy_after.png",
        "before": "working_copy_before.png",
        "after": "working_copy_after.png",
        "diff": "working_copy_diff.png",
    }
    _OUTPUT_NAMES = {
        "cdr": "output.cdr",
        "pdf": "output.pdf",
        "png": "output.png",
        "before": "before.png",
        "after": "after.png",
        "diff": "diff.png",
    }

    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace.resolve()

    def publish(self, task_id: str, settings: UiSettingsV1) -> tuple[int, dict[str, str]]:
        if not _TASK_ID_RE.fullmatch(task_id):
            raise ValueError("invalid task ID")
        run_root = (self.workspace / "runs" / task_id).resolve(strict=False)
        run_root.relative_to(self.workspace)
        output_root = (self.workspace / settings.output_subfolder / task_id).resolve(
            strict=False
        )
        output_root.relative_to(self.workspace)
        version = 1
        while (output_root / f"v{version:03d}").exists():
            version += 1
            if version > 9999:
                raise RuntimeError("output version limit reached")
        destination = output_root / f"v{version:03d}"
        destination.mkdir(parents=True, exist_ok=False)
        outputs: dict[str, str] = {}
        for kind, source_name in self._SOURCE_NAMES.items():
            if kind == "pdf" and not settings.default_pdf_export:
                continue
            if kind == "png" and not settings.default_png_export:
                continue
            source = (run_root / source_name).resolve(strict=False)
            source.relative_to(self.workspace)
            if not source.is_file():
                continue
            target = destination / self._OUTPUT_NAMES[kind]
            if settings.preview_quality == "standard" and kind in {
                "before",
                "after",
                "diff",
            }:
                with Image.open(source) as preview:
                    preview.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
                    preview.save(target, format="PNG", optimize=True)
            else:
                shutil.copy2(source, target)
            outputs[kind] = target.relative_to(self.workspace).as_posix()
        if "cdr" not in outputs:
            raise RuntimeError("editable CDR output is missing")
        return version, outputs

    def resolve(self, relative_path: str) -> Path:
        path = (self.workspace / relative_path).resolve(strict=False)
        path.relative_to(self.workspace)
        if not path.is_file():
            raise FileNotFoundError(relative_path)
        return path

    def resolve_folder(self, outputs: dict[str, str]) -> Path:
        if not outputs:
            raise FileNotFoundError("job has no outputs")
        first = self.resolve(next(iter(outputs.values())))
        return first.parent


class UiHealthProbe:
    def __init__(self, *, inventory: Path, workspace: Path, codex_executable: str) -> None:
        self.inventory = inventory.resolve()
        self.workspace = workspace.resolve()
        self.codex_executable = codex_executable

    @staticmethod
    def _corel_ready() -> tuple[bool, str]:
        if os.name != "nt":
            return False, "CorelDRAW requires Windows"
        try:
            completed = subprocess.run(
                ["tasklist.exe", "/FI", "IMAGENAME eq CorelDRW.exe", "/FO", "CSV", "/NH"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=5,
                check=False,
                shell=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False, "Corel process check failed"
        ready = completed.returncode == 0 and "CorelDRW.exe" in completed.stdout
        return ready, "CorelDRAW process detected" if ready else "Open CorelDRAW"

    def _mcp_ready(self) -> tuple[bool, str]:
        if not self.codex_executable:
            return False, "Codex CLI not found"
        try:
            completed = subprocess.run(
                [self.codex_executable, "mcp", "list"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=15,
                check=False,
                shell=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False, "MCP registration check failed"
        ready = completed.returncode == 0 and re.search(
            r"(?im)^corel_operator\s+.*\benabled\b", completed.stdout
        ) is not None
        return ready, "corel_operator MCP enabled" if ready else "Register corel_operator MCP"

    def _operator_ready(self) -> tuple[bool, str]:
        if not self.inventory.is_file():
            return False, "Inventory database is missing"
        try:
            self.workspace.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=self.workspace, delete=True):
                pass
        except OSError:
            return False, "Workspace is not writable"
        return True, "Inventory and workspace ready"

    def _codex_ready(self) -> tuple[bool, str]:
        if not self.codex_executable:
            return False, "Install/login Codex CLI"
        try:
            completed = subprocess.run(
                [self.codex_executable, "login", "status"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=15,
                check=False,
                shell=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False, "Codex authentication check failed"
        combined = f"{completed.stdout}\n{completed.stderr}".casefold()
        ready = completed.returncode == 0 and "logged in" in combined
        return ready, "Authenticated CLI available" if ready else "Run codex login"

    def probe(self) -> dict[str, Any]:
        corel_ready, corel_message = self._corel_ready()
        mcp_ready, mcp_message = self._mcp_ready()
        operator_ready, operator_message = self._operator_ready()
        codex_ready, codex_message = self._codex_ready()
        components = {
            "corel": {"status": "READY" if corel_ready else "OFFLINE", "message": corel_message},
            "mcp": {"status": "READY" if mcp_ready else "OFFLINE", "message": mcp_message},
            "operator": {
                "status": "READY" if operator_ready else "OFFLINE",
                "message": operator_message,
            },
            "codex": {
                "status": "READY" if codex_ready else "NEEDS_SETUP",
                "message": codex_message,
            },
        }
        return {
            "status": "READY" if all(
                component["status"] == "READY" for component in components.values()
            ) else "DEGRADED",
            "local_only": True,
            "components": components,
        }


def ensure_port_available(host: str, port: int) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.2)
        if probe.connect_ex((host, port)) == 0:
            raise RuntimeError(f"port {port} is already in use")


def open_local_path(path: Path) -> None:
    if os.name != "nt":
        raise RuntimeError("local open is supported only on Windows")
    os.startfile(str(path))  # type: ignore[attr-defined]


PathOpener = Callable[[Path], None]


__all__ = [
    "PathOpener",
    "UiHealthProbe",
    "UiJobRecordV1",
    "UiJobStore",
    "UiOutputManager",
    "UiSettingsStore",
    "UiSettingsV1",
    "ensure_port_available",
    "open_local_path",
]
