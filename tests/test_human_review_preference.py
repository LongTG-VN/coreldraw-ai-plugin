from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image
from pydantic import ValidationError

from training.evaluation.manual_review import write_manual_review_artifacts
from training.inference.baseline import generate_baseline_design
from training.preference.human_review import (
    CompletedHumanReviewV1,
    PreferencePairV1,
    build_preference_pair,
)
from training.schemas.design import DesignDocument
from training.tools.collect_human_reviews import collect


def _research_design(prompt: str, sample_id: str) -> DesignDocument:
    payload = generate_baseline_design(prompt, 210, 297).model_dump()
    payload["sample_id"] = sample_id
    payload["source"].update(
        {
            "name": "qwen3_genposter_research",
            "license_class": "research_only",
            "commercial_allowed": False,
        }
    )
    return DesignDocument.model_validate(payload)


def _review_package(tmp_path: Path) -> tuple[Path, Path]:
    left = _research_design("Poster spa", "review:left")
    right = _research_design("Poster spa", "review:right")
    left_design = tmp_path / "left.json"
    right_design = tmp_path / "right.json"
    left_design.write_text(left.model_dump_json(indent=2), encoding="utf-8")
    right_design.write_text(right.model_dump_json(indent=2), encoding="utf-8")
    left_preview = tmp_path / "left.png"
    right_preview = tmp_path / "right.png"
    Image.new("RGB", (80, 100), "#F4EBDD").save(left_preview)
    Image.new("RGB", (80, 100), "#244B41").save(right_preview)
    review_dir = tmp_path / "review"
    paths = write_manual_review_artifacts(
        prompt_id="spa_luxury",
        prompt="Poster spa",
        v02_preview_path=left_preview,
        v02_metrics={"combined": .82},
        v03_preview_path=right_preview,
        v03_metrics={"combined": .87},
        v02_design_path=left_design,
        v03_design_path=right_design,
        retrieved_references=[{"reference_id": "template:spa:hero_right", "score": .8}],
        output_dir=review_dir,
        left_key="v0.3",
        right_key="v0.3.1",
        left_label="V0.3 clean",
        right_label="V0.3.1 visual",
        artifact_type="v0.3_vs_v0.3.1_clean",
    )
    review = json.loads(paths["manual_review_template"].read_text(encoding="utf-8"))
    review.update(
        {
            "review_status": "completed",
            "preferred": "v0.3.1",
            "reviewer": "reviewer-01",
            "notes": "Hierarchy and composition are clearer.",
            "scores": {
                "v0.3": {"overall": 6, "hierarchy": 6, "typography": 6, "composition": 6},
                "v0.3.1": {"overall": 8, "hierarchy": 8, "typography": 7, "composition": 8},
            },
            "provenance": {
                "human_reviewed": True,
                "selection_source": "human",
                "heuristic_metrics_are_human_scores": False,
            },
        }
    )
    completed = review_dir / "manual_review.completed.json"
    completed.write_text(json.dumps(review, ensure_ascii=False), encoding="utf-8")
    return completed, paths["comparison"]


def test_completed_review_exports_research_only_preference_pair(tmp_path: Path) -> None:
    review, comparison = _review_package(tmp_path)
    pair = build_preference_pair(review_path=review, comparison_path=comparison)

    assert PreferencePairV1.model_validate(pair.model_dump()) == pair
    assert pair.chosen_variant == "v0.3.1"
    assert pair.rejected_variant == "v0.3"
    assert pair.chosen_design.sample_id == "review:right"
    assert pair.context_reference_ids == ["template:spa:hero_right"]
    assert pair.human_source.reviewer == "reviewer-01"
    assert pair.provenance["heuristic_selection_used_as_human_preference"] is False
    assert pair.research_only is True
    assert pair.commercial_allowed is False


def test_pending_or_heuristic_review_cannot_be_exported(tmp_path: Path) -> None:
    review, _ = _review_package(tmp_path)
    payload = json.loads(review.read_text(encoding="utf-8"))
    payload["review_status"] = "pending"
    payload["provenance"] = {
        "human_reviewed": False,
        "selection_source": None,
        "heuristic_metrics_are_human_scores": False,
    }

    with pytest.raises(ValidationError):
        CompletedHumanReviewV1.model_validate(payload)


def test_review_variant_identity_must_match_comparison(tmp_path: Path) -> None:
    review, comparison = _review_package(tmp_path)
    payload = json.loads(review.read_text(encoding="utf-8"))
    payload["scores"]["v0.4"] = payload["scores"].pop("v0.3")
    review.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="variants"):
        build_preference_pair(review_path=review, comparison_path=comparison)


def test_collector_writes_jsonl_and_refuses_overwrite(tmp_path: Path) -> None:
    review, _ = _review_package(tmp_path)
    output = tmp_path / "preferences.jsonl"

    path, count = collect([review.parent], output)
    record = json.loads(path.read_text(encoding="utf-8"))

    assert count == 1
    assert record["pair_id"].startswith("human:")
    assert record["provenance"]["human_approved"] is True
    with pytest.raises(FileExistsError, match="overwrite"):
        collect([review], output)
