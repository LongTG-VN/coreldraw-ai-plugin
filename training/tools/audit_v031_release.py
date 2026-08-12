"""Audit a complete v0.3.1 clean benchmark and its v0.3 comparison artifacts."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from PIL import Image

from training.schemas.design import DesignDocument


_PLACEHOLDER = re.compile(
    r"\[(?:ITEM|DESCRIPTION|PRICE|DISCOUNT|OFFER|DATE)_?\d*\]",
    re.I,
)
_REQUIRED_CANDIDATE_FILES = (
    "raw_output.txt",
    "generation.json",
    "validation.json",
    "design.json",
    "preview.png",
    "corel_operations.json",
    "score.json",
    "postprocess.json",
)


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def audit_release(
    *,
    benchmark_root: Path,
    comparison_root: Path,
    expected_prompts: int = 13,
    expected_candidates: int = 52,
) -> dict[str, Any]:
    benchmark_root = benchmark_root.resolve()
    comparison_root = comparison_root.resolve()
    summary = _read(benchmark_root / "benchmark_summary.json")
    generation_provenance = _read(benchmark_root / "generation_provenance.json")
    comparison = _read(comparison_root / "comparison_summary.json")
    run_dirs = sorted(path for path in (benchmark_root / "runs").iterdir() if path.is_dir())

    candidate_count = 0
    required_file_failures: list[str] = []
    strict_schema_valid = 0
    raw_schema_valid = 0
    fresh_candidates = 0
    resumed_candidates = 0
    audited_cache_candidates = 0
    invalid_identity_candidates: list[str] = []
    preview_valid = 0
    corel_compiled = 0
    truncated_count = 0
    unresolved_overflow_count = 0
    unresolved_overflow_candidates: list[str] = []
    winner_unresolved_overflow_count = 0
    missing_content_provenance: list[str] = []
    unmarked_placeholders: list[str] = []
    ungrounded_menu_prices: list[str] = []
    winner_artifacts_valid = 0

    for run_dir in run_dirs:
        brief = _read(run_dir / "brief.json")
        candidate_dirs = sorted(
            path for path in (run_dir / "candidates").iterdir() if path.is_dir()
        )
        for candidate_dir in candidate_dirs:
            candidate_count += 1
            key = f"{run_dir.name}/{candidate_dir.name}"
            missing = [
                name for name in _REQUIRED_CANDIDATE_FILES if not (candidate_dir / name).is_file()
            ]
            if missing:
                required_file_failures.append(f"{key}: {', '.join(missing)}")
                continue
            validation = _read(candidate_dir / "validation.json")
            strict_schema_valid += int(validation.get("strict_schema_valid") is True)
            raw_schema_valid += int(validation.get("raw_schema_valid") is True)
            generation = _read(candidate_dir / "generation.json").get("config", {})
            provenance = generation.get("generation_provenance")
            fresh_candidates += int(provenance == "fresh_generation")
            resumed_candidates += int(generation.get("resumed_verified_candidate") is True)
            audited_cache_candidates += int(generation.get("audited_raw_cache_reuse") is True)
            identity = generation.get("generation_identity")
            if not isinstance(identity, dict) or not generation.get(
                "generation_identity_sha256"
            ):
                invalid_identity_candidates.append(key)

            document_payload = _read(candidate_dir / "design.json")
            document = DesignDocument.model_validate(document_payload)
            for element in document.elements:
                if element.text is None:
                    continue
                metadata = element.metadata
                content = element.text.content
                if not metadata.get("content_provenance"):
                    missing_content_provenance.append(f"{key}/{element.id}")
                if _PLACEHOLDER.search(content) and not (
                    metadata.get("placeholder_only")
                    and metadata.get("requires_user_data")
                    and metadata.get("content_provenance")
                    in {"system_placeholder", "benchmark_placeholder"}
                ):
                    unmarked_placeholders.append(f"{key}/{element.id}")
                if (
                    brief.get("format") == "menu"
                    and metadata.get("role") == "price"
                    and metadata.get("content_provenance") == "model_generated_copy"
                ):
                    ungrounded_menu_prices.append(f"{key}/{element.id}:{content}")

            with Image.open(candidate_dir / "preview.png") as image:
                image.verify()
            preview_valid += 1
            operations = _read(candidate_dir / "corel_operations.json")
            corel_compiled += int(isinstance(operations, list) and bool(operations))
            postprocess = _read(candidate_dir / "postprocess.json")
            truncated_count += int(postprocess.get("truncated_count", 0))
            candidate_overflow = int(postprocess.get("unresolved_overflow_count", 0))
            unresolved_overflow_count += candidate_overflow
            if candidate_overflow:
                unresolved_overflow_candidates.append(f"{key}:{candidate_overflow}")

        final = run_dir / "final"
        final_required = ("design.json", "preview.png", "corel_operations.json", "selection.json")
        if all((final / name).is_file() for name in final_required):
            DesignDocument.model_validate(_read(final / "design.json"))
            with Image.open(final / "preview.png") as image:
                image.verify()
            operations = _read(final / "corel_operations.json")
            winner_artifacts_valid += int(isinstance(operations, list) and bool(operations))
            winner_id = str(_read(final / "selection.json")["winner"])
            winner_postprocess = _read(run_dir / "candidates" / winner_id / "postprocess.json")
            winner_unresolved_overflow_count += int(
                winner_postprocess.get("unresolved_overflow_count", 0)
            )

    rag_metrics = summary["v0.3_rag"]
    baseline = comparison["aggregates"]
    automatic_gates = {
        "prompt_count_exact": len(run_dirs) == expected_prompts,
        "candidate_count_exact": candidate_count == expected_candidates,
        "fresh_candidate_count_exact": fresh_candidates == expected_candidates,
        "summary_fresh_candidate_count_exact": generation_provenance.get(
            "fresh_candidate_count"
        )
        == expected_candidates,
        "no_resume": resumed_candidates == 0
        and generation_provenance.get("resumed_verified_candidate_count") == 0,
        "no_audited_cache_reuse": audited_cache_candidates == 0
        and generation_provenance.get("audited_raw_cache_reuse_count") == 0,
        "no_unsafe_reuse": generation_provenance.get("unsafe_reused_candidate_count") == 0,
        "identity_complete": not invalid_identity_candidates,
        "strict_schema_100_percent": strict_schema_valid == expected_candidates,
        "candidate_previews_100_percent": preview_valid == expected_candidates,
        "candidate_corel_compile_100_percent": corel_compiled == expected_candidates,
        "winner_artifacts_100_percent": winner_artifacts_valid == expected_prompts,
        "no_truncation": truncated_count == 0,
        "winner_no_unresolved_overflow": winner_unresolved_overflow_count == 0,
        "all_text_provenance_marked": not missing_content_provenance,
        "all_placeholders_marked": not unmarked_placeholders,
        "no_ungrounded_menu_prices": not ungrounded_menu_prices,
        "outside_canvas_zero": float(rag_metrics["outside_canvas"]) == 0,
        "overlap_near_zero": float(rag_metrics["overlap"]) <= 0.01,
        "text_fit_at_least_0_90": float(rag_metrics["text_fit"]) >= 0.90,
        "coverage_improved_over_v0_3": float(baseline["coverage"]["v0.3.1"])
        > float(baseline["coverage"]["v0.3"]),
        "hierarchy_not_worse_than_v0_3": float(baseline["hierarchy"]["v0.3.1"])
        >= float(baseline["hierarchy"]["v0.3"]),
        "human_preference_not_faked": summary.get("human_preference_collected") is False
        and comparison.get("human_preference_collected") is False,
    }
    return {
        "schema_version": "1.0",
        "artifact_type": "design_ai_v0.3.1_release_audit",
        "benchmark_root": str(benchmark_root),
        "comparison_root": str(comparison_root),
        "prompt_count": len(run_dirs),
        "candidate_count": candidate_count,
        "fresh_candidate_count": fresh_candidates,
        "resumed_verified_candidate_count": resumed_candidates,
        "audited_raw_cache_reuse_count": audited_cache_candidates,
        "strict_schema_valid_count": strict_schema_valid,
        "raw_schema_valid_count": raw_schema_valid,
        "preview_valid_count": preview_valid,
        "corel_compiled_count": corel_compiled,
        "winner_artifacts_valid_count": winner_artifacts_valid,
        "truncated_count": truncated_count,
        "unresolved_overflow_count": unresolved_overflow_count,
        "unresolved_overflow_candidates": unresolved_overflow_candidates,
        "winner_unresolved_overflow_count": winner_unresolved_overflow_count,
        "missing_required_files": required_file_failures,
        "invalid_identity_candidates": invalid_identity_candidates,
        "missing_content_provenance": missing_content_provenance,
        "unmarked_placeholders": unmarked_placeholders,
        "ungrounded_menu_prices": ungrounded_menu_prices,
        "automatic_gates": automatic_gates,
        "technically_safe": all(automatic_gates.values()),
        "human_reviewed": False,
        "production_ready": False,
        "commercial_allowed": False,
        "research_only": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark-root", type=Path, required=True)
    parser.add_argument("--comparison-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-prompts", type=int, default=13)
    parser.add_argument("--expected-candidates", type=int, default=52)
    args = parser.parse_args()
    report = audit_release(
        benchmark_root=args.benchmark_root,
        comparison_root=args.comparison_root,
        expected_prompts=args.expected_prompts,
        expected_candidates=args.expected_candidates,
    )
    _write(args.output.resolve(), report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["technically_safe"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
