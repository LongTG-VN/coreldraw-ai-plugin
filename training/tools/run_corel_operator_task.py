"""Plan or execute one conservative production-style operator task."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from training.company_archive.database import ArchiveDatabase
from training.corel_operator.agent import (
    AutonomousOperatorAgent,
    OperatorTaskRequestV1,
    OperatorTaskStatus,
)
from training.corel_operator.tools import OperatorToolService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive-root", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--file-id", required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--instruction", required=True)
    parser.add_argument("--execute", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    service = OperatorToolService(
        archive_root=args.archive_root,
        workspace=args.workspace,
        inventory=ArchiveDatabase(args.inventory),
    )
    result = AutonomousOperatorAgent(service).run(
        OperatorTaskRequestV1(
            file_id=args.file_id,
            task_id=args.task_id,
            instruction=args.instruction,
            execution_confirmed=args.execute,
        )
    )
    # Windows unattended shells may still use cp1252. Escaping non-ASCII keeps
    # the CLI machine-readable without changing the Unicode values in memory.
    print(json.dumps(result.model_dump(mode="json"), ensure_ascii=True, indent=2))
    return 0 if result.status in {
        OperatorTaskStatus.PLANNED,
        OperatorTaskStatus.AUTO_SUCCESS,
        OperatorTaskStatus.NEEDS_REVIEW,
    } else 2


if __name__ == "__main__":
    raise SystemExit(main())
