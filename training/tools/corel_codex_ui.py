"""Launch the local Corel Codex supervised-operator UI."""

from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn

from training.company_archive.database import ArchiveDatabase
from training.corel_operator.tools import OperatorToolService
from training.corel_operator.ui_app import CodexCliPlanBroker, create_corel_codex_ui_app


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive-root", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument(
        "--workspace",
        type=Path,
        default=Path("training/workspace/company_archive/operator_codex_ui"),
    )
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--host", default="127.0.0.1", choices=("127.0.0.1", "localhost"))
    parser.add_argument("--port", type=int, default=8004)
    parser.add_argument("--codex-timeout", type=int, default=180)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if not 1 <= args.port <= 65535:
        raise SystemExit("--port must be in 1..65535")
    if not 30 <= args.codex_timeout <= 600:
        raise SystemExit("--codex-timeout must be in 30..600 seconds")
    workspace = args.workspace.resolve()
    service = OperatorToolService(
        archive_root=args.archive_root,
        workspace=workspace,
        inventory=ArchiveDatabase(args.inventory),
    )
    planner = CodexCliPlanBroker(
        repo_root=args.repo_root,
        workspace=workspace,
        timeout_seconds=args.codex_timeout,
    )
    app = create_corel_codex_ui_app(
        service=service,
        planner=planner,
        workspace=workspace,
    )
    print(f"Open:\nhttp://127.0.0.1:{args.port}/corel-ui")
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
