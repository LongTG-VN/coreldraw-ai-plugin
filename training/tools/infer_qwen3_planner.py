"""Reload a trained adapter, infer, validate, compile, and compare baseline."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from training.evaluation.layout_metrics import evaluate_layout
from training.inference.baseline import generate_baseline_design
from training.inference.corel_compiler import compile_corel_operations
from training.inference.preview import render_preview
from training.inference.qwen3_planner import ModelOutputError, generate_with_checkpoint


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--width-mm", type=float, required=True)
    parser.add_argument("--height-mm", type=float, required=True)
    parser.add_argument("--max-new-tokens", type=int, default=1024)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    args.output.mkdir(parents=True, exist_ok=True)
    try:
        document, raw_output, parse_metadata = generate_with_checkpoint(
            checkpoint=args.checkpoint,
            model_id=config["model_id"],
            model_revision=config["model_revision"],
            prompt=args.prompt,
            width_mm=args.width_mm,
            height_mm=args.height_mm,
            max_new_tokens=args.max_new_tokens,
        )
    except ModelOutputError as exc:
        args.output.mkdir(parents=True, exist_ok=True)
        if exc.raw_output is not None:
            (args.output / "raw_output.txt").write_text(
                exc.raw_output,
                encoding="utf-8",
            )
        _write_json(args.output / "validation.json", {"error": str(exc)})
        raise
    operations = compile_corel_operations(
        document,
        width_mm=args.width_mm,
        height_mm=args.height_mm,
    )
    trained_metrics = evaluate_layout(document)
    baseline = generate_baseline_design(
        args.prompt,
        args.width_mm,
        args.height_mm,
    )
    baseline_metrics = evaluate_layout(baseline)
    comparison = {
        key: {
            "trained": trained_metrics[key],
            "baseline": baseline_metrics[key],
        }
        for key in trained_metrics
    }
    (args.output / "raw_output.txt").write_text(raw_output, encoding="utf-8")
    _write_json(
        args.output / "design.json",
        document.model_dump(mode="json", exclude_none=True),
    )
    _write_json(args.output / "corel_operations.json", operations)
    _write_json(args.output / "metrics.json", trained_metrics)
    _write_json(args.output / "baseline.design.json", baseline.model_dump(mode="json"))
    _write_json(args.output / "baseline.metrics.json", baseline_metrics)
    _write_json(args.output / "comparison.json", comparison)
    _write_json(args.output / "validation.json", parse_metadata)
    render_preview(document, args.output / "preview.png")
    render_preview(baseline, args.output / "baseline.preview.png")
    result = {
        "trained_model": True,
        "checkpoint": str(args.checkpoint.resolve()),
        "schema_validation": parse_metadata,
        "design": str((args.output / "design.json").resolve()),
        "corel_operations": str((args.output / "corel_operations.json").resolve()),
        "metrics": trained_metrics,
        "baseline_comparison": comparison,
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
