"""Generate, validate, score, and compile a deterministic baseline design."""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from training.evaluation.layout_metrics import evaluate_layout
from training.inference.baseline import generate_baseline_design
from training.inference.corel_compiler import compile_corel_operations
from training.inference.preview import render_preview


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate a structured non-model baseline design."
    )
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--width-mm", type=float, required=True)
    parser.add_argument("--height-mm", type=float, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--operations-output", type=Path)
    args = parser.parse_args()

    document = generate_baseline_design(
        args.prompt,
        args.width_mm,
        args.height_mm,
    )
    operations = compile_corel_operations(document)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        document.model_dump_json(indent=2, exclude_none=True) + "\n",
        encoding="utf-8",
    )
    operations_path = args.operations_output or args.output.with_name(
        f"{args.output.stem}.operations.json"
    )
    operations_path.write_text(
        json.dumps(operations, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    preview_path = render_preview(
        document,
        args.output.with_name(f"{args.output.stem}.preview.png"),
    )
    metrics = evaluate_layout(document)
    run_dir = args.output.parent.parent if args.output.parent.name == "samples" else None
    if run_dir is not None:
        (run_dir / "logs").mkdir(parents=True, exist_ok=True)
        (run_dir / "checkpoints").mkdir(parents=True, exist_ok=True)
        preflight_path = (
            Path(__file__).resolve().parents[1] / "workspace" / "preflight.json"
        )
        preflight = (
            json.loads(preflight_path.read_text(encoding="utf-8"))
            if preflight_path.is_file()
            else {}
        )
        git_commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
        ).stdout.strip()
        records = {
            "config.json": {
                "experiment_id": run_dir.name,
                "generator": "deterministic_structured_baseline_v0",
                "trained_model": False,
                "prompt": args.prompt,
                "width_mm": args.width_mm,
                "height_mm": args.height_mm,
                "seed": 42,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "git_commit": git_commit,
            },
            "environment.json": {
                "platform": platform.platform(),
                "python": platform.python_version(),
                "preflight": preflight,
            },
            "dataset.json": {
                "source": "synthetic_prompt_baseline",
                "license_class": "production_safe",
                "sample_count": 1,
            },
            "metrics.json": metrics,
        }
        for file_name, payload in records.items():
            (run_dir / file_name).write_text(
                json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
    result = {
        "status": "baseline_generated",
        "trained_model": False,
        "design": str(args.output.resolve()),
        "operations": str(operations_path.resolve()),
        "preview": str(preview_path),
        "metrics": metrics,
        "experiment": str(run_dir.resolve()) if run_dir is not None else None,
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
