from __future__ import annotations

from pathlib import Path
import subprocess

from training.corel_operator.census import (
    OperatorCensusRunner,
    classify_failure,
    select_census_rows,
)
from training.corel_operator.state import OperatorStateDatabase


def _rows(count: int) -> list[dict[str, object]]:
    return [
        {
            "file_id": f"file:{index:032x}",
            "cdr_candidate": True,
            "size_bytes": (index + 1) * 100,
        }
        for index in range(count)
    ]


def test_census_selection_is_deterministic_and_spans_size_range() -> None:
    rows = _rows(100)
    first = select_census_rows(rows, limit=20, seed="fixed")
    second = select_census_rows(list(reversed(rows)), limit=20, seed="fixed")
    assert [row["file_id"] for row in first] == [row["file_id"] for row in second]
    assert len(first) == 20
    sizes = [int(row["size_bytes"]) for row in first]
    assert min(sizes) <= 2000
    assert max(sizes) >= 8000


def test_census_selection_never_includes_non_cdr() -> None:
    rows = _rows(10)
    rows[0]["cdr_candidate"] = False
    selected = select_census_rows(rows, limit=20)
    assert len(selected) == 9
    assert rows[0] not in selected


def test_operator_state_is_resumable(tmp_path: Path) -> None:
    path = tmp_path / "state.sqlite"
    database = OperatorStateDatabase(path)
    database.put_census("source:one", "file:one", "COMPLETE", {"status": "COMPLETE"})
    reopened = OperatorStateDatabase(path)
    assert reopened.census_tokens() == {"source:one"}
    assert reopened.census_rows()[0]["result"]["status"] == "COMPLETE"


def test_batch_state_isolated_by_run_id(tmp_path: Path) -> None:
    database = OperatorStateDatabase(tmp_path / "state.sqlite")
    database.put_batch("run-a", "source:one", "COMPLETE", {"value": 1})
    database.put_batch("run-b", "source:one", "FAILED", {"value": 2})
    assert database.batch_rows("run-a")[0]["status"] == "COMPLETE"
    assert database.batch_rows("run-b")[0]["status"] == "FAILED"


def test_failure_classification_is_sanitized_category_only() -> None:
    assert classify_failure("RPC server unavailable") == "COREL_RUNTIME"
    assert classify_failure("could not save copy") == "COREL_SAVE_AS"
    assert classify_failure("random") == "UNKNOWN"


def test_isolated_census_timeout_is_persistable_and_recovers(
    tmp_path: Path, monkeypatch
) -> None:
    archive = tmp_path / "archive"
    workspace = tmp_path / "workspace"
    archive.mkdir()
    source = archive / "slow.cdr"
    source.write_bytes(b"source")
    runner = OperatorCensusRunner(archive_root=archive, workspace=workspace)

    class Recovery:
        closed = False

        def close_active_if_under(self, root: Path) -> bool:
            self.closed = True
            return True

    recovery = Recovery()
    runner.runtime = recovery  # type: ignore[assignment]

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args[0], timeout=kwargs["timeout"])

    monkeypatch.setattr(subprocess, "run", timeout)
    row = {
        "file_id": "file:" + "a" * 32,
        "absolute_path": str(source),
        "size_bytes": source.stat().st_size,
        "cdr_candidate": True,
    }
    result = runner._run_one_isolated(row, timeout_seconds=10)
    assert result["status"] == "FAILED"
    assert result["error_category"] == "TIMEOUT"
    assert result["source_unchanged"] is True
    assert recovery.closed is True
