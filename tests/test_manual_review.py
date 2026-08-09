from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from training.evaluation.manual_review import write_manual_review_artifacts


def _png(path: Path, color: str, size: tuple[int, int]) -> Path:
    Image.new("RGB", size, color).save(path, format="PNG")
    return path


def test_writes_pending_manual_review_package(tmp_path: Path) -> None:
    v02 = _png(tmp_path / "v02.png", "#ccaa88", (80, 120))
    v03 = _png(tmp_path / "v03.png", "#335544", (120, 80))
    reference_preview = _png(tmp_path / "reference.png", "#eeeecc", (20, 30))
    reference_design = tmp_path / "reference.json"
    reference_design.write_text("{}", encoding="utf-8")

    paths = write_manual_review_artifacts(
        prompt_id="dense_food_menu",
        prompt="Thiết kế menu 6 món",
        v02_preview_path=v02,
        v02_metrics={"combined_score": 0.65, "hierarchy": 0.69},
        v03_preview_path=v03,
        v03_metrics={"combined_score": 0.76, "hierarchy": 0.74},
        retrieved_references=[
            {
                "reference_id": "genposter-001",
                "score": 0.87,
                "match": {"category": 1.0, "style": 0.8},
                "preview_path": str(reference_preview),
                "design_document_path": str(reference_design),
                "research_only": True,
                "commercial_allowed": False,
            }
        ],
        output_dir=tmp_path / "review",
    )

    assert set(paths) == {
        "comparison",
        "side_by_side",
        "html",
        "manual_review_template",
    }
    assert all(path.is_file() for path in paths.values())
    comparison = json.loads(paths["comparison"].read_text(encoding="utf-8"))
    template = json.loads(
        paths["manual_review_template"].read_text(encoding="utf-8")
    )
    assert comparison["artifact_type"] == "v0.2_vs_v0.3_design_comparison"
    assert comparison["review_state"] == {
        "heuristic_metrics_are_human_scores": False,
        "human_reviewed": False,
        "preferred": None,
    }
    assert comparison["retrieved_references"][0]["commercial_allowed"] is False
    assert template["review_status"] == "pending"
    assert template["preferred"] is None
    assert template["reviewer"] is None
    assert all(
        score is None
        for variant in template["scores"].values()
        for score in variant.values()
    )
    assert template["provenance"] == {
        "heuristic_metrics_are_human_scores": False,
        "human_reviewed": False,
        "selection_source": None,
    }
    html_text = paths["html"].read_text(encoding="utf-8")
    assert "Human review pending" in html_text
    assert "not human preferences or human scores" in html_text
    with Image.open(paths["side_by_side"]) as image:
        assert image.format == "PNG"
        assert image.width > max(80, 120)
        assert image.height > max(80, 120)


def test_artifacts_are_deterministic_for_same_inputs(tmp_path: Path) -> None:
    v02 = _png(tmp_path / "v02.png", "red", (40, 60))
    v03 = _png(tmp_path / "v03.png", "blue", (60, 40))
    kwargs = {
        "prompt_id": "spa",
        "prompt": "Poster spa",
        "v02_preview_path": v02,
        "v02_metrics": {"score": 0.5},
        "v03_preview_path": v03,
        "v03_metrics": {"score": 0.6},
        "retrieved_references": [{"reference_id": "ref-1", "score": 0.9}],
    }
    first = write_manual_review_artifacts(output_dir=tmp_path / "a", **kwargs)
    second = write_manual_review_artifacts(output_dir=tmp_path / "b", **kwargs)

    for key in ("comparison", "side_by_side", "html", "manual_review_template"):
        assert first[key].read_bytes() == second[key].read_bytes()


@pytest.mark.parametrize("field", ["v02_preview_path", "v03_preview_path"])
def test_rejects_missing_preview_path(tmp_path: Path, field: str) -> None:
    existing = _png(tmp_path / "existing.png", "white", (10, 10))
    kwargs = {
        "prompt_id": "spa",
        "prompt": "Poster spa",
        "v02_preview_path": existing,
        "v02_metrics": {},
        "v03_preview_path": existing,
        "v03_metrics": {},
        "retrieved_references": [],
        "output_dir": tmp_path / "review",
    }
    kwargs[field] = tmp_path / "missing.png"

    with pytest.raises(FileNotFoundError, match=field):
        write_manual_review_artifacts(**kwargs)


def test_rejects_bad_metadata_without_writing(tmp_path: Path) -> None:
    preview = _png(tmp_path / "preview.png", "white", (10, 10))
    output_dir = tmp_path / "review"

    with pytest.raises(ValueError, match="non-finite"):
        write_manual_review_artifacts(
            prompt_id="spa",
            prompt="Poster spa",
            v02_preview_path=preview,
            v02_metrics={"score": float("nan")},
            v03_preview_path=preview,
            v03_metrics={},
            retrieved_references=[],
            output_dir=output_dir,
        )
    assert not output_dir.exists()


def test_validates_reference_identity_score_and_paths(tmp_path: Path) -> None:
    preview = _png(tmp_path / "preview.png", "white", (10, 10))
    common = {
        "prompt_id": "spa",
        "prompt": "Poster spa",
        "v02_preview_path": preview,
        "v02_metrics": {},
        "v03_preview_path": preview,
        "v03_metrics": {},
        "output_dir": tmp_path / "review",
    }

    with pytest.raises(ValueError, match="reference_id"):
        write_manual_review_artifacts(retrieved_references=[{"score": 0.4}], **common)
    with pytest.raises(ValueError, match="0..1"):
        write_manual_review_artifacts(
            retrieved_references=[{"reference_id": "ref", "score": 1.1}], **common
        )
    with pytest.raises(FileNotFoundError, match="design_document_path"):
        write_manual_review_artifacts(
            retrieved_references=[
                {
                    "reference_id": "ref",
                    "score": 0.5,
                    "design_document_path": str(tmp_path / "missing.json"),
                }
            ],
            **common,
        )
