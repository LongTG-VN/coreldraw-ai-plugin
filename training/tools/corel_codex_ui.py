"""Launch the local Corel Codex supervised-operator UI."""

from __future__ import annotations

import argparse
import json
import shutil
import threading
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path
from typing import Literal

import uvicorn

from training.company_archive.database import ArchiveDatabase
from training.corel_operator.tools import OperatorToolService
from training.corel_operator.ui_app import CodexCliPlanBroker, create_corel_codex_ui_app
from training.corel_operator.ui_state import UiHealthProbe, ensure_port_available


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive-root", type=Path)
    parser.add_argument(
        "--inventory",
        type=Path,
        default=Path("training/workspace/company_archive/archive.sqlite"),
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        default=Path("training/workspace/company_archive/operator_codex_ui"),
    )
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--host", default="127.0.0.1", choices=("127.0.0.1", "localhost"))
    parser.add_argument("--port", type=int, default=8004)
    parser.add_argument("--codex-timeout", type=int, default=180)
    parser.add_argument("--open-browser", action="store_true")
    parser.add_argument("--ensure-corel", action="store_true")
    parser.add_argument("--preflight-only", action="store_true")
    return parser


def _archive_root(args: argparse.Namespace, inventory: ArchiveDatabase) -> Path:
    if args.archive_root is not None:
        return args.archive_root.resolve()
    with inventory.connect() as database:
        row = database.execute(
            "SELECT root FROM scan_state WHERE completed=1 ORDER BY updated_at DESC LIMIT 1"
        ).fetchone()
    if row is None:
        raise RuntimeError("--archive-root is required because inventory has no completed scan")
    root = Path(str(row[0])).resolve()
    if not root.is_dir():
        raise RuntimeError("the inventory archive root is no longer available")
    return root


def _ensure_corel_available() -> None:
    from corel_bridge import corel_bridge

    if not corel_bridge.connect():
        raise RuntimeError("CorelDRAW could not be started or connected")


def _existing_ui_ready(port: int) -> bool:
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/v1/corel-ui/status",
        headers={"Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=2) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError, urllib.error.URLError):
        return False
    return bool(
        isinstance(payload, dict)
        and payload.get("local_only")
        and payload.get("source_policy") == "READ_ONLY"
        and payload.get("status") in {"READY", "DEGRADED"}
    )


def main() -> int:
    args = build_parser().parse_args()
    if not 1 <= args.port <= 65535:
        raise SystemExit("--port must be in 1..65535")
    if not 30 <= args.codex_timeout <= 600:
        raise SystemExit("--codex-timeout must be in 30..600 seconds")
    inventory_path = args.inventory.resolve()
    workspace = args.workspace.resolve()
    inventory = ArchiveDatabase(inventory_path)
    try:
        archive_root = _archive_root(args, inventory)
        if args.ensure_corel:
            _ensure_corel_available()
    except RuntimeError as exc:
        raise SystemExit(f"STARTUP BLOCKED: {exc}") from exc
    codex_executable = shutil.which("codex") or ""
    health_probe = UiHealthProbe(
        inventory=inventory_path,
        workspace=workspace,
        codex_executable=codex_executable,
    )
    health = health_probe.probe()
    for name, component in health["components"].items():
        print(f"{name.upper()}: {component['status']} - {component['message']}")
    if args.preflight_only:
        return 0 if health["status"] == "READY" else 2
    if health["status"] != "READY":
        raise SystemExit("STARTUP BLOCKED: resolve OFFLINE/NEEDS_SETUP prerequisites above")
    try:
        ensure_port_available("127.0.0.1", args.port)
    except RuntimeError as exc:
        if _existing_ui_ready(args.port):
            url = f"http://127.0.0.1:{args.port}/corel-ui"
            print(f"READY - existing Corel AI Operator is already running\nOpen:\n{url}")
            if args.open_browser:
                webbrowser.open(url)
            return 0
        raise SystemExit(f"STARTUP BLOCKED: {exc}") from exc
    service = OperatorToolService(
        archive_root=archive_root,
        workspace=workspace,
        inventory=inventory,
    )
    planner = CodexCliPlanBroker(
        repo_root=args.repo_root,
        workspace=workspace,
        timeout_seconds=args.codex_timeout,
    )
    first_start = True
    while True:
        lifecycle_action: list[Literal["shutdown", "restart"]] = []
        server_holder: list[uvicorn.Server] = []

        def request_lifecycle(action: Literal["shutdown", "restart"]) -> None:
            lifecycle_action.append(action)
            if server_holder:
                server_holder[0].should_exit = True

        app = create_corel_codex_ui_app(
            service=service,
            planner=planner,
            workspace=workspace,
            health_probe=health_probe,
            lifecycle_callback=request_lifecycle,
        )
        config = uvicorn.Config(app, host="127.0.0.1", port=args.port, log_level="info")
        server = uvicorn.Server(config)
        server_holder.append(server)
        url = f"http://127.0.0.1:{args.port}/corel-ui"
        print(f"READY\nOpen:\n{url}")
        if args.open_browser and first_start:
            threading.Timer(1.0, webbrowser.open, args=(url,)).start()
        first_start = False
        server.run()
        if lifecycle_action != ["restart"]:
            break
        print("Restarting Corel AI Operator safely...")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
