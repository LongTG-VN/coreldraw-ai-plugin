from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from training.tools.audit_v031_release import audit_release
from training.tools.build_reference_corpus import _generic_document


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _fixture(tmp_path: Path) -> tuple[Path, Path]:
    benchmark = tmp_path / "benchmark"
    comparison = tmp_path / "comparison"
    run = benchmark / "runs" / "spa"
    candidate = run / "candidates" / "candidate_01"
    document = _generic_document("spa", "centered", ["cream", "gold"])
    for element in document.elements:
        if element.text is not None:
            element.metadata["content_provenance"] = "model_generated_copy"
    payload = document.model_dump(mode="json")
    _write(run / "brief.json", {"format": "poster"})
    _write(candidate / "design.json", payload)
    (candidate / "raw_output.txt").write_text("{}", encoding="utf-8")
    _write(
        candidate / "generation.json",
        {
            "config": {
                "generation_provenance": "fresh_generation",
                "resumed_verified_candidate": False,
                "audited_raw_cache_reuse": False,
                "generation_identity": {"schema_version": "1.0"},
                "generation_identity_sha256": "abc",
            }
        },
    )
    _write(
        candidate / "validation.json",
        {"strict_schema_valid": True, "raw_schema_valid": False},
    )
    Image.new("RGB", (40, 40), "white").save(candidate / "preview.png")
    _write(candidate / "corel_operations.json", [{"op": "page_resize"}])
    _write(candidate / "score.json", {"final_score": .9})
    _write(
        candidate / "postprocess.json",
        {"truncated_count": 0, "unresolved_overflow_count": 0},
    )
    final = run / "final"
    _write(final / "design.json", payload)
    Image.new("RGB", (40, 40), "white").save(final / "preview.png")
    _write(final / "corel_operations.json", [{"op": "page_resize"}])
    _write(final / "selection.json", {"winner": "candidate_01"})
    _write(
        benchmark / "benchmark_summary.json",
        {
            "v0.3_rag": {"outside_canvas": 0, "overlap": 0, "text_fit": 1},
            "human_preference_collected": False,
        },
    )
    _write(
        benchmark / "generation_provenance.json",
        {
            "fresh_candidate_count": 1,
            "resumed_verified_candidate_count": 0,
            "audited_raw_cache_reuse_count": 0,
            "unsafe_reused_candidate_count": 0,
        },
    )
    _write(
        comparison / "comparison_summary.json",
        {
            "aggregates": {
                "coverage": {"v0.3": .3, "v0.3.1": .4},
                "hierarchy": {"v0.3": .7, "v0.3.1": .7},
            },
            "human_preference_collected": False,
        },
    )
    return benchmark, comparison


def test_v031_release_audit_requires_complete_fresh_safe_artifacts(tmp_path: Path) -> None:
    benchmark, comparison = _fixture(tmp_path)

    report = audit_release(
        benchmark_root=benchmark,
        comparison_root=comparison,
        expected_prompts=1,
        expected_candidates=1,
    )

    assert report["technically_safe"] is True
    assert report["fresh_candidate_count"] == 1
    assert report["raw_schema_valid_count"] == 0
    assert report["winner_unresolved_overflow_count"] == 0
    assert report["human_reviewed"] is False
    assert report["production_ready"] is False


def test_v031_release_audit_rejects_missing_text_provenance(tmp_path: Path) -> None:
    benchmark, comparison = _fixture(tmp_path)
    design_path = benchmark / "runs" / "spa" / "candidates" / "candidate_01" / "design.json"
    payload = json.loads(design_path.read_text(encoding="utf-8"))
    next(item for item in payload["elements"] if item.get("text"))["metadata"].pop(
        "content_provenance"
    )
    _write(design_path, payload)

    report = audit_release(
        benchmark_root=benchmark,
        comparison_root=comparison,
        expected_prompts=1,
        expected_candidates=1,
    )

    assert report["technically_safe"] is False
    assert report["automatic_gates"]["all_text_provenance_marked"] is False
