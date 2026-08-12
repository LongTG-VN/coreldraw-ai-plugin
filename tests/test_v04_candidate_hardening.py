from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from training.preference.v04.diagnostics import (
    summarize_human_reviews,
    write_diagnostic_snapshot,
)
from training.preference.v04.hardening import (
    CandidateInvariantV1,
    QualityFloorResultV1,
    apply_candidate_style_variant,
    assert_candidate_group_locked,
    evaluate_quality_floor,
    invariant_from_document,
    structural_diversity,
    variants_for_category,
)
from training.preference.v04.models import HumanReviewV1, OptionalReviewScoresV1
from training.schemas.design import DesignDocument


def _case(case_id: str) -> tuple[DesignDocument, dict]:
    width, height = (500, 100) if case_id == "signage" else (400, 400)
    case = {
        "source_prompt_id": f"{case_id}_pilot",
        "headline": {"spa": "SPA AN NHIÊN", "cafe": "MỘC CAFE", "sale": "MEGA SALE", "menu": "BẾP NHÀ", "signage": "PHỞ GIA TRUYỀN"}[case_id],
        "subheadline": "Nội dung benchmark",
        "body": "Nội dung được khóa",
        "cta": "LIÊN HỆ",
        "benchmark_sample_data": True,
        "customer_provided": False,
    }
    if case_id == "sale":
        case["discounts"] = ["30%"]
    if case_id == "menu":
        case["items"] = [
            {"name": f"Món {index}", "description": f"Mô tả {index}", "price": f"{40 + index}K"}
            for index in range(1, 6)
        ]

    def element(
        element_id: str,
        *,
        role: str,
        box: tuple[float, float, float, float],
        content: str | None = None,
        asset_ref: str | None = None,
    ) -> dict:
        x, y, box_width, box_height = box
        return {
            "id": element_id,
            "name": element_id,
            "type": "text" if content is not None else ("svg" if role == "logo" else "image"),
            "bbox": {"x": x * width, "y": y * height, "width": box_width * width, "height": box_height * height},
            "bbox_norm": {"x": x, "y": y, "width": box_width, "height": box_height},
            "z_index": 2,
            "layer": "content" if content is not None else "assets",
            "text": ({"content": content, "font_family": "DejaVuSans.ttf", "font_size": 12, "font_weight": 500, "alignment": "left"} if content is not None else None),
            "visual": {},
            "asset_ref": asset_ref,
            "metadata": {"role": role, "asset_role": role} if asset_ref else {"role": role},
        }

    asset_role = "logo" if case_id == "signage" else ("product" if case_id == "sale" else "hero")
    assets = [
        {"id": f"{case_id}_{asset_role}", "source": f"fixtures/{case_id}.png", "type": "logo" if asset_role == "logo" else "bitmap", "metadata": {"sha256": "a" * 64, "role": asset_role}},
    ]
    if case_id != "signage":
        assets.append({"id": f"{case_id}_logo", "source": f"fixtures/{case_id}.svg", "type": "svg", "metadata": {"sha256": "b" * 64, "role": "logo"}})
    elements = [
        element("headline", role="headline", box=(.06, .12, .44, .14), content=case["headline"]),
        element("body", role="body", box=(.06, .34, .42, .12), content=case["body"]),
        element("cta", role="cta", box=(.06, .76, .30, .10), content=case["cta"]),
        element("hero", role=asset_role, box=(.55, .12, .38, .62), asset_ref=f"{case_id}_{asset_role}"),
    ]
    if case_id != "signage":
        elements.append(element("logo", role="logo", box=(.06, .03, .26, .07), asset_ref=f"{case_id}_logo"))
    if case_id == "sale":
        elements.append(element("benchmark_sale_offer", role="promotion", box=(.55, .42, .30, .10), content="GIẢM 30%"))
    if case_id == "menu":
        elements = [item for item in elements if item["id"] not in {"body", "hero"}]
        elements.append(element("hero", role="hero", box=(.70, .04, .24, .20), asset_ref="menu_hero"))
        for index, item in enumerate(case["items"], 1):
            y = .30 + (index - 1) * .10
            elements.append(element(f"menu_item_{index:02d}", role="menu_item", box=(.06, y, .65, .07), content=f"{item['name']}\n{item['description']}"))
            elements.append(element(f"menu_price_{index:02d}", role="price", box=(.78, y, .14, .06), content=item["price"]))
    document = DesignDocument.model_validate(
        {
            "sample_id": f"fixture:{case_id}",
            "source": {"name": "fixture", "split": "test", "license_class": "project_owned", "upstream_id": case_id, "commercial_allowed": True},
            "canvas": {"width": width, "height": height, "unit": "px"},
            "category": case_id,
            "elements": elements,
            "assets": assets,
            "metadata": {"brief_id": case["source_prompt_id"], "phase1_1_case_id": case_id, "candidate_invariant_brief": case},
        }
    )
    return document, case


def _invariant(case_id: str) -> CandidateInvariantV1:
    document, case = _case(case_id)
    return invariant_from_document(
        document,
        brief_id=case["source_prompt_id"],
        brief_payload=case,
    )


def test_candidate_invariant_hashes_are_stable() -> None:
    first = _invariant("sale")
    second = _invariant("sale")
    assert first == second
    assert first.discounts == ["30%"]
    assert len(first.asset_hashes) == 2


@pytest.mark.parametrize(
    ("mutation", "field"),
    [
        ({"headline": "ANOTHER BRAND"}, "content_lock_hash"),
        ({"discounts": ["50%"]}, "business_value_hash"),
        ({"offers": ["MUA 1 TẶNG 1"]}, "business_value_hash"),
        ({"prices": ["99K"]}, "business_value_hash"),
    ],
)
def test_business_content_mutation_rejected(mutation: dict, field: str) -> None:
    source = _invariant("sale")
    changed = source.model_copy(update={**mutation, field: "f" * 64})
    group = [source, source, source, changed]
    with pytest.raises(ValueError, match=field):
        assert_candidate_group_locked(group)


def test_menu_value_mutation_rejected() -> None:
    source = _invariant("menu")
    changed = source.model_copy(
        update={
            "menu_items": [{"name": "Changed", "description": "", "price": "10K"}],
            "content_lock_hash": "e" * 64,
        }
    )
    with pytest.raises(ValueError, match="content_lock_hash"):
        assert_candidate_group_locked([source, source, source, changed])


def test_asset_and_canvas_mutation_rejected() -> None:
    source = _invariant("spa")
    asset_changed = source.model_copy(update={"asset_lock_hash": "a" * 64})
    with pytest.raises(ValueError, match="asset_lock_hash"):
        assert_candidate_group_locked([source, source, source, asset_changed])
    canvas_changed = source.model_copy(update={"canvas_hash": "b" * 64})
    with pytest.raises(ValueError, match="canvas_hash"):
        assert_candidate_group_locked([source, source, source, canvas_changed])


@pytest.mark.parametrize("case_id", ["spa", "cafe", "sale", "menu", "signage"])
def test_composition_families_are_bounded_and_diverse(case_id: str) -> None:
    variants = variants_for_category(case_id)
    assert len(variants) == 4
    assert len({item.layout_family for item in variants}) >= 3
    assert all(not hasattr(item, "headline") for item in variants)


def test_style_variants_preserve_locks_and_are_structurally_diverse() -> None:
    source, case = _case("spa")
    before = invariant_from_document(
        source, brief_id=case["source_prompt_id"], brief_payload=case
    )
    documents = {}
    for index, variant in enumerate(variants_for_category("spa")):
        document = apply_candidate_style_variant(source, variant)
        after = invariant_from_document(
            document, brief_id=case["source_prompt_id"], brief_payload=case
        )
        assert after.content_lock_hash == before.content_lock_hash
        assert after.asset_lock_hash == before.asset_lock_hash
        assert after.business_value_hash == before.business_value_hash
        assert after.canvas_hash == before.canvas_hash
        documents[str(index)] = document
    report = structural_diversity(documents)
    assert report["passes"] is True
    assert report["distinct_layout_family_count"] == 4
    assert report["minimum_pairwise_candidate_diversity"] >= .16


def test_near_duplicate_group_fails_diversity() -> None:
    document, _ = _case("spa")
    report = structural_diversity({str(index): document for index in range(4)})
    assert report["passes"] is False
    assert report["minimum_pairwise_candidate_diversity"] == 0


def test_quality_floor_records_transparent_diagnostics() -> None:
    document, _ = _case("spa")
    result = evaluate_quality_floor(
        document,
        {
            "coverage": .05,
            "outside_canvas_rate": 0,
            "overlap_ratio": 0,
            "text_fit_rate": 1,
            "text_overflow_count": 0,
        },
        regeneration_count=3,
    )
    assert result.passed is False
    assert "EXCESSIVE_WHITESPACE" in result.reasons
    assert result.regeneration_count == 3
    with pytest.raises(ValidationError):
        QualityFloorResultV1(passed=True, reasons=["LOW_DIVERSITY"], metrics={}, regeneration_count=0)


def test_regeneration_cap_is_bounded() -> None:
    with pytest.raises(ValidationError):
        QualityFloorResultV1(
            passed=False,
            reasons=["TECHNICAL_FAILURE"],
            metrics={},
            regeneration_count=6,
        )


def test_pilot_rating_field_is_optional_and_prominent() -> None:
    assert OptionalReviewScoresV1().overall_quality is None
    assert OptionalReviewScoresV1(overall_quality=7).overall_quality == 7
    with pytest.raises(ValidationError):
        OptionalReviewScoresV1(overall_quality=11)


def _human_review(review_id: str, choice: str = "both_bad") -> HumanReviewV1:
    return HumanReviewV1.model_validate(
        {
            "review_id": f"review:{review_id:0>24}",
            "pair_id": f"pair:{review_id:0>24}",
            "brief_id": "spa_luxury",
            "prompt": "spa brief",
            "category": "spa",
            "design_a_id": "pilot:spa:A",
            "design_b_id": "pilot:spa:B",
            "choice": choice,
            "scores": None,
            "notes": None,
            "confidence": None,
            "reviewer": "Long",
            "session_id": "session:" + "1" * 24,
            "created_at": datetime(2026, 8, 12, tzinfo=timezone.utc),
            "source": "human",
            "human_verified": True,
            "provenance": {"selection_source": "human_ui_action"},
            "license_class": "research_only",
            "commercial_allowed": False,
        }
    )


def test_old_human_snapshot_is_immutable_and_diagnostic_only(tmp_path: Path) -> None:
    reviews = tmp_path / "reviews/session"
    reviews.mkdir(parents=True)
    review = _human_review("a")
    (reviews / "a.json").write_text(review.model_dump_json(), encoding="utf-8")
    output = tmp_path / "snapshot"
    summary = write_diagnostic_snapshot(tmp_path / "reviews", output)
    assert summary["human_review_count"] == 1
    assert summary["snapshot_class"] == "diagnostic_generation_v1"
    assert summary["eligible_for_preference_training"] is False
    with pytest.raises(FileExistsError, match="immutable"):
        write_diagnostic_snapshot(tmp_path / "reviews", output)


def test_human_only_labels_remain_enforced() -> None:
    human = _human_review("b", choice="a")
    assert summarize_human_reviews([human])["human_only_validation"] is True
    payload = human.model_dump(mode="json")
    payload["provenance"] = {"selection_source": "automatic"}
    with pytest.raises(ValidationError):
        HumanReviewV1.model_validate(payload)
