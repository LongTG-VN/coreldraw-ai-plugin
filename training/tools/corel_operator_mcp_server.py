"""Start the local policy-gated Corel operator MCP server."""

from __future__ import annotations

import argparse
from pathlib import Path

from training.company_archive.database import ArchiveDatabase
from training.corel_operator.mcp_server import create_mcp_server
from training.corel_operator.tools import OperatorToolService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive-root", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument(
        "--transport",
        choices=("stdio", "streamable-http"),
        default="stdio",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8012)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if not 1 <= args.port <= 65535:
        raise SystemExit("--port must be in 1..65535")
    service = OperatorToolService(
        archive_root=args.archive_root,
        workspace=args.workspace,
        inventory=ArchiveDatabase(args.inventory),
    )
    server = create_mcp_server(service, host=args.host, port=args.port)
    server.run(transport=args.transport)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
