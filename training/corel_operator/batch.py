"""Resumable per-file isolation for Corel operator pilots."""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from training.corel_operator.models import MutationPlanV1, OperatorResultClass
from training.corel_operator.policy import sanitize_error, source_token
from training.corel_operator.service import SafeCorelOperator
from training.corel_operator.state import OperatorStateDatabase


PlanFactory = Callable[[dict[str, Any], str], MutationPlanV1 | None]


class OperatorBatchRunner:
    """Run bounded copies sequentially with persisted per-file outcomes."""

    def __init__(
        self,
        *,
        run_id: str,
        archive_root: Path,
        workspace: Path,
        operator: SafeCorelOperator,
        state: OperatorStateDatabase,
        max_attempts: int = 2,
        timeout_seconds: float = 180.0,
    ) -> None:
        if max_attempts not in {1, 2}:
            raise ValueError("max_attempts must be 1 or 2")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.run_id = run_id
        self.archive_root = archive_root.resolve()
        self.workspace = workspace.resolve()
        self.operator = operator
        self.state = state
        self.max_attempts = max_attempts
        self.timeout_seconds = timeout_seconds

    def run(self, rows: list[dict[str, Any]], plan_factory: PlanFactory) -> list[dict[str, Any]]:
        completed = {
            row["source_token"]
            for row in self.state.batch_rows(self.run_id)
            if row["status"] in {"COMPLETE", "NEEDS_REVIEW", "UNSUPPORTED", "FAILED"}
        }
        for row in rows:
            source = Path(str(row["absolute_path"])).resolve()
            token = source_token(source, self.archive_root)
            if token in completed:
                continue
            plan = plan_factory(row, token)
            if plan is None:
                result = {
                    "result": OperatorResultClass.UNSUPPORTED.value,
                    "source_token": token,
                    "reason": "no bounded mutation plan available",
                }
                self.state.put_batch(self.run_id, token, "UNSUPPORTED", result)
                continue
            outcome: dict[str, Any] | None = None
            for attempt in range(1, self.max_attempts + 1):
                attempt_root = self.workspace / self.run_id / token.removeprefix("source:") / f"attempt_{attempt}"
                target = attempt_root / "working_copy.cdr"
                started = time.perf_counter()
                try:
                    execution = self.operator.execute(
                        source_path=source,
                        archive_root=self.archive_root,
                        workspace=self.workspace,
                        working_copy_path=target,
                        plan=plan,
                    )
                    outcome = execution.model_dump(mode="json")
                except Exception as exc:
                    outcome = {
                        "result": OperatorResultClass.FAILED.value,
                        "source_token": token,
                        "error_code": "UNHANDLED_BATCH_FAILURE",
                        "error": sanitize_error(exc, archive_root=self.archive_root),
                    }
                elapsed = time.perf_counter() - started
                outcome["attempt"] = attempt
                outcome["elapsed_seconds"] = elapsed
                if elapsed > self.timeout_seconds:
                    outcome["result"] = OperatorResultClass.FAILED.value
                    outcome["error_code"] = "TIMEOUT_EXCEEDED"
                if outcome["result"] not in {OperatorResultClass.FAILED.value}:
                    break
            assert outcome is not None
            status = (
                "COMPLETE"
                if outcome["result"] in {
                    OperatorResultClass.AUTO_SUCCESS.value,
                    OperatorResultClass.SUCCESS_WITH_WARNING.value,
                }
                else outcome["result"]
            )
            self.state.put_batch(
                self.run_id,
                token,
                status,
                outcome,
                attempt_count=int(outcome["attempt"]),
            )
        return self.state.batch_rows(self.run_id)
