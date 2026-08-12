"""Audit a completed Design AI v0.3 benchmark without loading the model.

This tool is deliberately artifact-only. It verifies that a clean benchmark
contains the expected runs/candidates, has no raw-generation cache reuse, keeps
all required artifacts, and reports raw-schema recovery and synthetic user-data
limitations honestly. It never changes scores or design files.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

_PRICE_RE = re.compile(r"(?:\d[\d.,]*\s*(?:k|đ|vnd|usd|\$|€))", re.IGNORECASE)
_SYNTHETIC_MENU_RE = re.compile(r"\bmón\s*\d+\b", re.IGNORECASE)
_REQUIRED_CANDIDATE_FILES = (
    "raw_output.txt",
    "generation.json",
    "validation.json",
    "metrics.json",
    "score.json",
    "design.json",
    "corel_operations.json",
    "preview.png",
    "postprocess.json",
)


def _read_json(path: Path) -> Any:
    if not path.is_file():
        raise FileNotFoundError(f"required JSON artifact does not exist: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_run_dir(root: Path, row: dict[str, Any]) -> Path:
    local = root / "runs" / str(row["prompt_id"])
    if local.is_dir():
        return local.resolve()
    recorded = row.get("v0.3", {}).get("run_dir")
    return Path(recorded).expanduser().resolve() if recorded else local.resolve()


def _candidate_audit(candidate_dir: Path) -> dict[str, Any]:
    missing = [name for name in _REQUIRED_CANDIDATE_FILES if not (candidate_dir / name).is_file()]
    validation = (
        _read_json(candidate_dir / "validation.json")
        if (candidate_dir / "validation.json").is_file()
        else {}
    )
    generation = (
        _read_json(candidate_dir / "generation.json")
        if (candidate_dir / "generation.json").is_file()
        else {}
    )
    config = generation.get("config") if isinstance(generation, dict) else {}
    config = config if isinstance(config, dict) else {}
    reused = bool(
        config.get("reused_raw_output")
        or config.get("reused_from")
        or config.get("cache_hit")
        or config.get("generation_cache_hit")
    )

    synthetic_elements = 0
    invented_synthetic_values = 0
    examples: list[str] = []
    design_path = candidate_dir / "design.json"
    if design_path.is_file():
        design = _read_json(design_path)
        for element in design.get("elements", []):
            metadata = element.get("metadata") or {}
            if not metadata.get("synthetic_brief_completion"):
                continue
            synthetic_elements += 1
            role = str(metadata.get("role") or "").casefold()
            content = str((element.get("text") or {}).get("content") or "")
            looks_invented = (
                role == "price" and _PRICE_RE.search(content) is not None
            ) or (
                role == "menu_item" and _SYNTHETIC_MENU_RE.search(content) is not None
            )
            if looks_invented:
                invented_synthetic_values += 1
                if len(examples) < 5:
                    examples.append(content)

    duration = float(generation.get("duration_seconds", 0.0) or 0.0)
    strict_valid = bool(validation.get("strict_schema_valid", False))
    raw_valid = bool(validation.get("raw_schema_valid", False))
    return {
        "candidate_id": candidate_dir.name,
        "artifact_complete": not missing,
        "missing_artifacts": missing,
        "strict_schema_valid": strict_valid,
        "raw_schema_valid": raw_valid,
        "schema_recovery_required": strict_valid and not raw_valid,
        "reused_generation": reused,
        "positive_generation_duration": duration > 0,
        "generation_duration_seconds": duration,
        "synthetic_user_data_element_count": synthetic_elements,
        "invented_synthetic_value_count": invented_synthetic_values,
        "invented_synthetic_examples": examples,
    }


def audit_benchmark(
    benchmark_root: Path,
    *,
    expected_prompt_count: int = 13,
    expected_candidates_per_prompt: int = 4,
) -> dict[str, Any]:
    root = benchmark_root.expanduser().resolve()
    summary = _read_json(root / "benchmark_summary.json")
    rows = _read_json(root / "benchmark_rows.json")
    if not isinstance(rows, list):
        raise ValueError("benchmark_rows.json must contain a list")

    candidates: list[dict[str, Any]] = []
    missing_run_dirs: list[str] = []
    for row in rows:
        run_dir = _resolve_run_dir(root, row)
        if not run_dir.is_dir():
            missing_run_dirs.append(str(run_dir))
            continue
        candidate_dirs = sorted((run_dir / "candidates").glob("candidate_*"))
        candidates.extend(_candidate_audit(path) for path in candidate_dirs)

    total = len(candidates)
    expected_total = expected_prompt_count * expected_candidates_per_prompt
    strict_valid_count = sum(bool(item["strict_schema_valid"]) for item in candidates)
    raw_valid_count = sum(bool(item["raw_schema_valid"]) for item in candidates)
    recovery_count = sum(bool(item["schema_recovery_required"]) for item in candidates)
    reused_count = sum(bool(item["reused_generation"]) for item in candidates)
    positive_duration_count = sum(bool(item["positive_generation_duration"]) for item in candidates)
    artifact_complete_count = sum(bool(item["artifact_complete"]) for item in candidates)
    synthetic_count = sum(int(item["synthetic_user_data_element_count"]) for item in candidates)
    invented_count = sum(int(item["invented_synthetic_value_count"]) for item in candidates)

    automatic_gates_pass = bool(summary.get("v0.3_complete", False))
    stable = all(
        (
            len(rows) == expected_prompt_count,
            total == expected_total,
            not missing_run_dirs,
            artifact_complete_count == total,
            strict_valid_count == total,
            reused_count == 0,
            positive_duration_count == total,
            automatic_gates_pass,
        )
    )

    v02 = summary.get("v0.2_fair_replay") or {}
    v03 = summary.get("v0.3_rag") or {}
    warnings: list[str] = []
    if raw_valid_count < total:
        warnings.append(
            f"raw model schema validity is {raw_valid_count}/{total}; "
            "validated candidates depend on explicit recovery"
        )
    if invented_count:
        warnings.append(
            f"{invented_count} synthetic menu/business values are placeholders, "
            "not customer-supplied data"
        )
    if v02 and v03 and float(v03.get("coverage", 0)) < float(v02.get("coverage", 0)):
        warnings.append(
            "v0.3 coverage is lower than the fair v0.2 replay; visual density remains a known limitation"
        )

    return {
        "schema_version": "1.0",
        "release": "Design AI v0.3",
        "status": "stable_research_checkpoint" if stable else "needs_attention",
        "stable_research_checkpoint": stable,
        "production_ready": False,
        "commercial_allowed": False,
        "benchmark_root": str(root),
        "expected": {
            "prompt_count": expected_prompt_count,
            "candidates_per_prompt": expected_candidates_per_prompt,
            "candidate_count": expected_total,
        },
        "observed": {
            "prompt_count": len(rows),
            "candidate_count": total,
            "artifact_complete_count": artifact_complete_count,
            "strict_schema_valid_count": strict_valid_count,
            "raw_schema_valid_count": raw_valid_count,
            "schema_recovery_required_count": recovery_count,
            "reused_generation_count": reused_count,
            "positive_generation_duration_count": positive_duration_count,
            "synthetic_user_data_element_count": synthetic_count,
            "invented_synthetic_value_count": invented_count,
            "missing_run_dirs": missing_run_dirs,
        },
        "rates": {
            "strict_schema_validity": strict_valid_count / total if total else 0.0,
            "raw_schema_validity": raw_valid_count / total if total else 0.0,
            "schema_recovery_rate": recovery_count / total if total else 0.0,
        },
        "automatic_success_gates_pass": automatic_gates_pass,
        "benchmark_metrics": {
            "v0.2_fair": v02,
            "v0.3_clean": v03,
            "combined_score_improvement_percent": summary.get(
                "combined_score_improvement_percent"
            ),
        },
        "warnings": warnings,
        "candidate_audits": candidates,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark-root", type=Path, required=True)
    parser.add_argument("--expected-prompts", type=int, default=13)
    parser.add_argument("--candidates-per-prompt", type=int, default=4)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = audit_benchmark(
        args.benchmark_root,
        expected_prompt_count=args.expected_prompts,
        expected_candidates_per_prompt=args.candidates_per_prompt,
    )
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["stable_research_checkpoint"] else 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["audit_benchmark"]
