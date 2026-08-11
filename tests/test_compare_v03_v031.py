from __future__ import annotations

import json
from pathlib import Path

from PIL import Image
import pytest

from training.tools.compare_v03_v031 import compare


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _benchmark(root: Path, *, score: float, coverage: float) -> None:
    run = root / "runs" / "spa"
    winner = run / "candidates" / "candidate_01"
    winner.mkdir(parents=True)
    Image.new("RGB", (120, 180), "white").save(winner / "preview.png")
    _write(winner / "design.json", {"sample_id": "spa"})
    _write(run / "retrieval.json", {"results": []})
    metrics = {
        "combined_score": score,
        "technical_score": .9,
        "overlap": 0.0,
        "spacing": .9,
        "hierarchy": .7,
        "text_fit": 1.0,
        "coverage": coverage,
        "outside_canvas": 0.0,
        "schema_valid": True,
    }
    _write(
        root / "benchmark_rows.json",
        [
            {
                "prompt_id": "spa",
                "prompt": "Poster spa",
                "v0.3": {
                    "winner": "candidate_01",
                    "winner_metrics": metrics,
                    "winner_preview_path": str(winner / "preview.png"),
                    "winner_design_path": str(winner / "design.json"),
                    "candidate_diversity": .2,
                    "run_dir": str(run),
                },
            }
        ],
    )
    _write(
        root / "benchmark_summary.json",
        {
            "candidate_provenance": {
                "fresh_generation_count": 4,
                "resumed_verified_candidate_count": 0,
                "raw_cache_reuse_count": 0,
            }
        },
    )


def test_compare_clean_releases_writes_pending_human_artifacts(tmp_path: Path) -> None:
    old = tmp_path / "old"
    new = tmp_path / "new"
    _benchmark(old, score=.8, coverage=.3)
    _benchmark(new, score=.88, coverage=.45)

    summary = compare(v03=old, v031=new, output=tmp_path / "comparison")

    assert summary["prompt_count"] == 1
    assert summary["fresh_candidates"] == 4
    assert summary["unsafe_reused_candidates"] == 0
    assert summary["combined_improvement_percent"] == pytest.approx(10.0)
    assert summary["aggregates"]["coverage"]["v0.3.1"] == .45
    assert summary["human_preference_collected"] is False
    assert (tmp_path / "comparison" / "contact_sheet_all_13.png").is_file()
    template = json.loads(
        (tmp_path / "comparison" / "runs" / "spa" / "manual_review.template.json").read_text()
    )
    assert template["preferred"] is None
    assert template["provenance"]["human_reviewed"] is False
