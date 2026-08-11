from __future__ import annotations

import json
from pathlib import Path

from training.tools.audit_v03_release import audit_benchmark


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _fixture(tmp_path: Path, *, reused: bool = False) -> Path:
    root = tmp_path / "benchmark"
    run_dir = root / "runs" / "dense_food_menu"
    candidate = run_dir / "candidates" / "candidate_01"
    candidate.mkdir(parents=True)

    _write_json(
        root / "benchmark_summary.json",
        {
            "v0.3_complete": True,
            "combined_score_improvement_percent": 11.2,
            "v0.2_fair_replay": {"coverage": 0.45},
            "v0.3_rag": {"coverage": 0.31},
        },
    )
    _write_json(
        root / "benchmark_rows.json",
        [
            {
                "prompt_id": "dense_food_menu",
                "v0.3": {"run_dir": str(run_dir)},
            }
        ],
    )
    (candidate / "raw_output.txt").write_text("{}", encoding="utf-8")
    _write_json(
        candidate / "generation.json",
        {
            "duration_seconds": 1.25,
            "config": {"reused_raw_output": reused} if reused else {},
        },
    )
    _write_json(
        candidate / "validation.json",
        {
            "strict_schema_valid": True,
            "raw_schema_valid": False,
            "recovery_steps": ["schema_recovery"],
        },
    )
    _write_json(candidate / "metrics.json", {})
    _write_json(candidate / "score.json", {})
    _write_json(
        candidate / "design.json",
        {
            "elements": [
                {
                    "metadata": {
                        "synthetic_brief_completion": True,
                        "role": "menu_item",
                    },
                    "text": {"content": "Món 01\nMô tả ngắn"},
                },
                {
                    "metadata": {
                        "synthetic_brief_completion": True,
                        "role": "price",
                    },
                    "text": {"content": "39K"},
                },
            ]
        },
    )
    _write_json(candidate / "corel_operations.json", [])
    (candidate / "preview.png").write_bytes(b"placeholder")
    _write_json(candidate / "postprocess.json", {})
    return root


def test_audit_accepts_clean_research_checkpoint_and_reports_limitations(
    tmp_path: Path,
) -> None:
    report = audit_benchmark(
        _fixture(tmp_path),
        expected_prompt_count=1,
        expected_candidates_per_prompt=1,
    )

    assert report["stable_research_checkpoint"] is True
    assert report["production_ready"] is False
    assert report["observed"]["candidate_count"] == 1
    assert report["observed"]["strict_schema_valid_count"] == 1
    assert report["observed"]["raw_schema_valid_count"] == 0
    assert report["observed"]["schema_recovery_required_count"] == 1
    assert report["observed"]["reused_generation_count"] == 0
    assert report["observed"]["invented_synthetic_value_count"] == 2
    assert report["rates"]["raw_schema_validity"] == 0
    assert len(report["warnings"]) >= 2


def test_audit_rejects_reused_generation(tmp_path: Path) -> None:
    report = audit_benchmark(
        _fixture(tmp_path, reused=True),
        expected_prompt_count=1,
        expected_candidates_per_prompt=1,
    )

    assert report["stable_research_checkpoint"] is False
    assert report["observed"]["reused_generation_count"] == 1
