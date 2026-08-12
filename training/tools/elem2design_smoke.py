"""Create a guarded elem2design smoke launch plan; never fake execution."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from training.experiments.elem2design import (
    assess_launch,
    load_experiment_config,
)
from training.tools.bootstrap import REPO_ROOT


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Dry-run or execute a hardware/data-gated elem2design smoke run."
    )
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--write-report", action="store_true")
    args = parser.parse_args()

    config = load_experiment_config(args.config)
    report = assess_launch(config, repo_root=REPO_ROOT)
    report.update(
        {
            "experiment_id": config["experiment_id"],
            "actually_executed": False,
            "config": str(args.config.resolve()),
        }
    )
    if args.execute:
        if not report["executable"]:
            report["execution_error"] = "Execution blocked by verified gates."
        else:
            completed = subprocess.run(
                report["command"],
                cwd=REPO_ROOT / config["upstream"]["local_path"],
                check=False,
            )
            report["actually_executed"] = True
            report["returncode"] = completed.returncode
            report["status"] = "completed" if completed.returncode == 0 else "failed"

    if args.write_report:
        output_dir = REPO_ROOT / config["data_gate"]["elem2design_adapter"]
        output_dir.mkdir(parents=True, exist_ok=True)
        report_path = output_dir / "launch_plan.json"
        report_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        report["report_path"] = str(report_path.resolve())
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if not args.execute or report.get("status") == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
