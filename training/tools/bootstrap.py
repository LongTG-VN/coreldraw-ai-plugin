from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
TRAINING_ROOT = REPO_ROOT / "training"
CONFIG_PATH = TRAINING_ROOT / "config" / "datasets.json"
WORKSPACE_ROOT = TRAINING_ROOT / "workspace"
VENDOR_ROOT = TRAINING_ROOT / "vendor"


def load_registry(path: Path = CONFIG_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def workspace_directories() -> list[Path]:
    return [
        TRAINING_ROOT / "data" / "research",
        TRAINING_ROOT / "data" / "production" / "synthetic",
        TRAINING_ROOT / "data" / "production" / "private_corel",
        TRAINING_ROOT / "artifacts" / "runs",
        WORKSPACE_ROOT / "probes",
        VENDOR_ROOT,
    ]


def build_plan(profile: str, clone_upstreams: bool = False) -> dict[str, Any]:
    registry = load_registry()
    profiles = registry.get("profiles", {})
    if profile not in profiles:
        raise ValueError(f"Unknown profile: {profile}")

    return {
        "profile": profile,
        "max_samples": int(profiles[profile]["max_samples"]),
        "directories": [str(path.relative_to(REPO_ROOT)) for path in workspace_directories()],
        "clone_upstreams": clone_upstreams,
        "upstreams": registry.get("upstreams", {}) if clone_upstreams else {},
        "dataset_downloads": "none",
        "license_policy": "research and production namespaces stay separated",
    }


def _clone_upstream(name: str, info: dict[str, Any]) -> dict[str, Any]:
    destination = VENDOR_ROOT / name
    if destination.exists():
        return {
            "name": name,
            "status": "skipped_existing",
            "path": str(destination),
        }

    git = shutil.which("git")
    if git is None:
        return {
            "name": name,
            "status": "error",
            "error": "git is not available",
        }

    url = str(info.get("url") or "").strip()
    if not url:
        return {
            "name": name,
            "status": "error",
            "error": "missing upstream URL",
        }

    completed = subprocess.run(
        [git, "clone", "--depth", "1", url, str(destination)],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        return {
            "name": name,
            "status": "error",
            "error": (completed.stderr or completed.stdout or "git clone failed").strip(),
        }
    return {
        "name": name,
        "status": "cloned",
        "path": str(destination),
        "url": url,
    }


def apply_plan(plan: dict[str, Any]) -> dict[str, Any]:
    for path in workspace_directories():
        path.mkdir(parents=True, exist_ok=True)

    clone_results: list[dict[str, Any]] = []
    if plan.get("clone_upstreams"):
        upstreams = plan.get("upstreams", {})
        ordered = sorted(
            upstreams.items(),
            key=lambda item: int(item[1].get("priority", 999)),
        )
        for name, info in ordered:
            clone_results.append(_clone_upstream(name, info))

    state = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "plan": plan,
        "clone_results": clone_results,
    }
    WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)
    state_path = WORKSPACE_ROOT / "bootstrap_state.json"
    state_path.write_text(
        json.dumps(state, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return state


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prepare a safe local workspace for design-AI training."
    )
    parser.add_argument(
        "--profile",
        choices=("smoke", "prototype", "research"),
        default="smoke",
    )
    parser.add_argument(
        "--clone-upstreams",
        action="store_true",
        help="Include shallow cloning of configured research repositories.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Create directories and perform requested clones. Without this flag, only print the plan.",
    )
    args = parser.parse_args()

    plan = build_plan(args.profile, clone_upstreams=args.clone_upstreams)
    print(json.dumps(plan, indent=2, ensure_ascii=False))

    if not args.apply:
        print("Dry run only. Re-run with --apply to make local changes.")
        return 0

    state = apply_plan(plan)
    print(json.dumps(state, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
