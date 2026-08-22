"""Crash-safe plan job persistence and duplicate-execution prevention."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from pathlib import Path

from training.corel_agent.models import (
    AgentJobStatus,
    CorelAgentRequestV1,
    CorelOperatorJobV1,
    CorelPlanEnvelopeV1,
    PlanValidationV1,
)


_TRANSITIONS: dict[AgentJobStatus, set[AgentJobStatus]] = {
    AgentJobStatus.CREATED: {AgentJobStatus.INSPECTED, AgentJobStatus.FAILED},
    AgentJobStatus.INSPECTED: {AgentJobStatus.PLANNED, AgentJobStatus.NEEDS_REVIEW, AgentJobStatus.FAILED},
    AgentJobStatus.PLANNED: {AgentJobStatus.VALIDATED, AgentJobStatus.NEEDS_REVIEW, AgentJobStatus.FAILED},
    AgentJobStatus.VALIDATED: {AgentJobStatus.WAITING_CONFIRMATION, AgentJobStatus.EXECUTING, AgentJobStatus.COMPLETED},
    AgentJobStatus.WAITING_CONFIRMATION: {AgentJobStatus.EXECUTING, AgentJobStatus.FAILED},
    AgentJobStatus.EXECUTING: {AgentJobStatus.VALIDATING, AgentJobStatus.ROLLED_BACK, AgentJobStatus.FAILED},
    AgentJobStatus.VALIDATING: {AgentJobStatus.COMPLETED, AgentJobStatus.NEEDS_REVIEW, AgentJobStatus.ROLLED_BACK, AgentJobStatus.FAILED},
    AgentJobStatus.COMPLETED: set(),
    AgentJobStatus.NEEDS_REVIEW: set(),
    AgentJobStatus.ROLLED_BACK: set(),
    AgentJobStatus.FAILED: set(),
}


def normalize_request(value: str) -> str:
    return " ".join(value.casefold().split())


def plan_hash(envelope: CorelPlanEnvelopeV1) -> str:
    payload = json.dumps(envelope.model_dump(mode="json"), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def task_fingerprint(
    source_sha256: str,
    request: CorelAgentRequestV1,
    envelope: CorelPlanEnvelopeV1,
) -> str:
    if not re.fullmatch(r"[a-f0-9]{64}", source_sha256):
        raise ValueError("source SHA-256 is invalid")
    value = "\n".join((source_sha256, normalize_request(request.instruction), plan_hash(envelope)))
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def versioned_output_name(design_id: str, job_id: str, version: int, suffix: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", design_id):
        raise ValueError("design ID is not safe for output naming")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,95}", job_id):
        raise ValueError("job ID is not safe for output naming")
    if not 1 <= version <= 9999 or suffix.casefold() not in {".cdr", ".pdf", ".png"}:
        raise ValueError("output version or extension is invalid")
    return f"{design_id}__{job_id}__v{version:03d}{suffix.casefold()}"


class CorelJobStore:
    def __init__(self, path: Path) -> None:
        self.path = path.resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute(
                """CREATE TABLE IF NOT EXISTS jobs (
                job_id TEXT PRIMARY KEY,
                fingerprint TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )"""
            )

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def put(self, job: CorelOperatorJobV1) -> CorelOperatorJobV1:
        with self.connect() as db:
            db.execute(
                """INSERT INTO jobs(job_id,fingerprint,status,payload_json)
                VALUES(?,?,?,?) ON CONFLICT(job_id) DO UPDATE SET
                fingerprint=excluded.fingerprint,status=excluded.status,
                payload_json=excluded.payload_json,updated_at=CURRENT_TIMESTAMP""",
                (
                    job.job_id,
                    job.task_fingerprint,
                    job.status.value,
                    job.model_dump_json(),
                ),
            )
        return job

    def get(self, job_id: str) -> CorelOperatorJobV1:
        with self.connect() as db:
            row = db.execute("SELECT payload_json FROM jobs WHERE job_id=?", (job_id,)).fetchone()
        if row is None:
            raise KeyError(job_id)
        return CorelOperatorJobV1.model_validate_json(str(row[0]))

    def find_by_fingerprint(self, fingerprint: str) -> CorelOperatorJobV1 | None:
        with self.connect() as db:
            row = db.execute(
                "SELECT payload_json FROM jobs WHERE fingerprint=?", (fingerprint,)
            ).fetchone()
        return None if row is None else CorelOperatorJobV1.model_validate_json(str(row[0]))

    def transition(self, job_id: str, status: AgentJobStatus) -> CorelOperatorJobV1:
        job = self.get(job_id)
        if status not in _TRANSITIONS[job.status]:
            raise ValueError(f"invalid job transition: {job.status.value} -> {status.value}")
        return self.put(job.model_copy(update={"status": status}))

    def create_validated(
        self,
        request: CorelAgentRequestV1,
        envelope: CorelPlanEnvelopeV1,
        validation: PlanValidationV1,
        *,
        source_sha256: str,
    ) -> tuple[CorelOperatorJobV1, bool]:
        fingerprint = task_fingerprint(source_sha256, request, envelope)
        existing = self.find_by_fingerprint(fingerprint)
        if existing is not None:
            return existing, True
        job = CorelOperatorJobV1(
            job_id=request.request_id,
            document_id=request.document_id,
            request=request.instruction,
            planner=envelope.provenance,
            plan_hash=plan_hash(envelope),
            task_fingerprint=fingerprint,
            risk=validation.risk_level,
            status=(
                AgentJobStatus.VALIDATED
                if validation.accepted and not validation.review_required
                else AgentJobStatus.NEEDS_REVIEW
            ),
            dry_run=request.execution_mode.value != "EXECUTE_CONFIRMED",
            execution_confirmed=request.execution_mode.value == "EXECUTE_CONFIRMED",
            validation=validation,
            audit=[{"event": "PLAN_VALIDATED", "source": "corel_agent"}],
        )
        return self.put(job), False


__all__ = [
    "CorelJobStore",
    "normalize_request",
    "plan_hash",
    "task_fingerprint",
    "versioned_output_name",
]
