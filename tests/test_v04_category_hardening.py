from __future__ import annotations

from datetime import datetime, timezone

import pytest

from training.preference.v04.category_hardening import (
    apply_category_hardening_v2,
    category_group_diversity,
    evaluate_category_quality_floor_v2,
    profile_for_category,
    variants_for_category_v2,
)
from training.preference.v04.hardening import invariant_from_document
from training.preference.v04.models import (
    CandidateArtifactV1,
    HumanReviewV1,
    ReviewSessionV1,
)
from training.preference.v04.pairing import tournament_pairs
from training.preference.v04.review_analytics import (
    QueueIdentityV1,
    build_review_analytics,
    category_failure_ranking,
    normalize_category,
    reconstruct_review_provenance,
    select_weak_categories,
)
from training.schemas.design import DesignDocument
from training.tools.human_review_server import resolve_queue_path


def _review(
    index: int,
    *,
    session_id: str,
    category: str,
    choice: str,
    generation_version: str | None = None,
) -> HumanReviewV1:
    provenance = {"selection_source": "human_ui_action"}
    if generation_version:
        provenance["generation_version"] = generation_version
    return HumanReviewV1.model_validate(
        {
            "review_id": f"review:{index:024x}",
            "pair_id": f"pair:{index:024x}",
            "brief_id": f"brief_{category}_{index}",
            "prompt": f"Brief {category}",
            "category": category,
            "design_a_id": f"design:{category}:{index}:a",
            "design_b_id": f"design:{category}:{index}:b",
            "choice": choice,
            "scores": None,
            "notes": None,
            "confidence": None,
            "reviewer": "Long",
            "session_id": session_id,
            "created_at": datetime(2026, 8, 12, 8, index % 60, tzinfo=timezone.utc),
            "source": "human",
            "human_verified": True,
            "provenance": provenance,
            "license_class": "research_only",
            "commercial_allowed": False,
        }
    )


def _session(session_id: str, queue_hash: str) -> ReviewSessionV1:
    return ReviewSessionV1.model_construct(
        schema_version="1.0",
        session_id=session_id,
        reviewer="Long",
        queue_sha256=queue_hash,
        seed=1,
        ordered_pair_ids=[],
        blind_mappings={},
        skipped_pair_ids=[],
        started_at=datetime(2026, 8, 12, tzinfo=timezone.utc),
        completed_at=None,
    )


def test_provenance_reconstruction_uses_session_queue_hash() -> None:
    old_hash, new_hash = "a" * 64, "b" * 64
    old_session = "session:" + "1" * 24
    new_session = "session:" + "2" * 24
    queues = [
        QueueIdentityV1(queue_id="old", generation_version="diagnostic_generation_v1", queue_path="old.jsonl", queue_sha256=old_hash),
        QueueIdentityV1(queue_id="pilot", generation_version="candidate_generation_v2_pilot", queue_path="pilot.jsonl", queue_sha256=new_hash),
    ]
    rows = reconstruct_review_provenance(
        [
            _review(1, session_id=old_session, category="poster_sale", choice="both_bad"),
            _review(2, session_id=new_session, category="sale", choice="a", generation_version="candidate_generation_v2_pilot"),
        ],
        [_session(old_session, old_hash), _session(new_session, new_hash)],
        queues,
    )
    assert rows[0].queue_id == "old"
    assert rows[0].generation_version == "diagnostic_generation_v1"
    assert rows[0].provenance_status == "queue_hash"
    assert rows[1].queue_id == "pilot"
    assert rows[1].provenance_status == "queue_hash_and_record"
    assert all(item.normalized_category == "sale" for item in rows)


def test_unknown_or_conflicting_provenance_is_not_guessed() -> None:
    session_id = "session:" + "3" * 24
    queue = QueueIdentityV1(queue_id="pilot", generation_version="candidate_generation_v2_pilot", queue_path="pilot.jsonl", queue_sha256="c" * 64)
    conflict = reconstruct_review_provenance(
        [_review(3, session_id=session_id, category="spa", choice="a", generation_version="wrong")],
        [_session(session_id, "c" * 64)],
        [queue],
    )[0]
    assert conflict.generation_version == "unknown"
    assert conflict.queue_id == "unknown"
    assert "GENERATION_VERSION_CONFLICT" in conflict.provenance_issues


def test_alias_normalization_is_explicit() -> None:
    assert normalize_category("poster_sale") == "sale"
    assert normalize_category("card_visit") == "business_card"
    assert normalize_category("my_pham") == "cosmetics"
    assert normalize_category("nha_hang") == "menu"
    assert normalize_category("unmapped") == "unmapped"


def test_failure_ranking_selects_three_evidence_backed_pilot_categories() -> None:
    queue_hash = "d" * 64
    session_id = "session:" + "4" * 24
    queue = QueueIdentityV1(queue_id="pilot", generation_version="candidate_generation_v2_pilot", queue_path="pilot.jsonl", queue_sha256=queue_hash)
    reviews = []
    index = 10
    for category, choices in {
        "sale": ["both_bad"] * 4,
        "signage": ["both_bad", "both_bad", "both_bad", "a"],
        "spa": ["both_bad", "both_bad", "a", "b"],
        "cafe": ["both_bad", "a", "a", "b"],
        "menu": ["both_bad", "a", "b", "tie"],
        "nail": ["both_bad", "both_bad"],
    }.items():
        for choice in choices:
            reviews.append(_review(index, session_id=session_id, category=category, choice=choice, generation_version="candidate_generation_v2_pilot"))
            index += 1
    rows = reconstruct_review_provenance(reviews, [_session(session_id, queue_hash)], [queue])
    ranking = category_failure_ranking(rows, generation_version="candidate_generation_v2_pilot")
    assert [item["category"] for item in ranking[:3]] == ["sale", "signage", "spa"]
    assert next(item for item in ranking if item["category"] == "nail")["sample_note"] == "LOW_CONFIDENCE"
    assert [item["category"] for item in select_weak_categories(ranking)] == ["sale", "signage", "spa"]
    analytics = build_review_analytics(rows)
    assert analytics["overall"]["both_bad"] == 13
    assert analytics["both_bad_exported_as_preference"] is False
    assert analytics["automated_preference_labels"] == 0


def _design(category: str) -> tuple[DesignDocument, dict]:
    width, height = ((500, 100) if category == "signage" else ((400, 120) if category == "spa" else (108, 135)))
    case = {
        "source_prompt_id": f"{category}_pilot",
        "headline": {"spa": "SPA AN NHIÊN", "sale": "MEGA SALE", "signage": "PHỞ GIA TRUYỀN"}[category],
        "subheadline": "Chăm sóc da chuyên sâu" if category == "spa" else "Hương vị Việt",
        "body": "Không gian thư giãn và chăm sóc da" if category == "spa" else None,
        "cta": "Đặt lịch hôm nay" if category == "spa" else ("MUA NGAY" if category == "sale" else None),
        "discounts": ["30%"] if category == "sale" else [],
        "benchmark_sample_data": True,
        "customer_provided": False,
    }

    def element(element_id: str, role: str, box: tuple[float, float, float, float], *, content: str | None = None, asset_ref: str | None = None) -> dict:
        x, y, w, h = box
        return {
            "id": element_id,
            "name": element_id,
            "type": "text" if content is not None else ("svg" if role == "logo" else "image"),
            "bbox": {"x": x * width, "y": y * height, "width": w * width, "height": h * height},
            "bbox_norm": {"x": x, "y": y, "width": w, "height": h},
            "z_index": 2,
            "layer": "content" if content is not None else "assets",
            "text": ({"content": content, "font_family": "DejaVuSans.ttf", "font_size": 12, "font_weight": 500, "alignment": "left"} if content is not None else None),
            "visual": {},
            "asset_ref": asset_ref,
            "metadata": {"role": role, "asset_role": role} if asset_ref else {"role": role},
        }

    focal_role = "logo" if category == "signage" else ("product" if category == "sale" else "hero")
    focal_id = f"{category}_{focal_role}"
    assets = [{"id": focal_id, "source": f"fixtures/{category}.png", "type": "logo" if focal_role == "logo" else "bitmap", "metadata": {"sha256": "a" * 64, "role": focal_role}}]
    elements = [
        element("headline", "headline", (.06, .15, .42, .18), content=case["subheadline"] if category in {"spa", "signage"} else case["headline"]),
        element("focal", focal_role, (.53, .12, .40, .68), asset_ref=focal_id),
    ]
    if category != "signage":
        assets.append({"id": f"{category}_logo", "source": f"fixtures/{category}.svg", "type": "svg", "metadata": {"sha256": "b" * 64, "role": "logo"}})
        elements.append(element("logo", "logo", (.06, .04, .25, .08), asset_ref=f"{category}_logo"))
    if case["body"]:
        elements.append(element("body", "body", (.06, .45, .38, .12), content=case["body"]))
    if case["cta"]:
        elements.append(element("cta", "cta", (.06, .73, .30, .10), content=case["cta"]))
    if category == "sale":
        elements.append(element("offer", "promotion", (.06, .40, .36, .13), content="GIẢM 30%"))
    document = DesignDocument.model_validate({
        "sample_id": f"fixture:{category}",
        "source": {"name": "fixture", "split": "test", "license_class": "project_owned", "upstream_id": category, "commercial_allowed": True},
        "canvas": {"width": width, "height": height, "unit": "px"},
        "category": category,
        "elements": elements,
        "assets": assets,
        "metadata": {"brief_id": case["source_prompt_id"], "phase1_1_case_id": category, "candidate_invariant_brief": case},
    })
    return document, case


@pytest.mark.parametrize("category", ["sale", "signage", "spa"])
def test_category_profiles_are_scoped_bounded_and_diverse(category: str) -> None:
    profile = profile_for_category(category)
    variants = variants_for_category_v2(category)
    assert profile.category == category
    assert len(variants) == 4
    assert len({item.layout_family for item in variants}) == 4
    assert all(item.category == category for item in variants)
    with pytest.raises(ValueError, match="scoped"):
        profile_for_category("cafe")


@pytest.mark.parametrize("category", ["sale", "signage", "spa"])
def test_category_hardening_preserves_content_assets_business_values_and_canvas(category: str) -> None:
    source, case = _design(category)
    before = invariant_from_document(source, brief_id=case["source_prompt_id"], brief_payload=case)
    documents = {}
    for variant in variants_for_category_v2(category):
        hardened = apply_category_hardening_v2(source, variant)
        after = invariant_from_document(hardened, brief_id=case["source_prompt_id"], brief_payload=case)
        assert after.content_lock_hash == before.content_lock_hash
        assert after.asset_lock_hash == before.asset_lock_hash
        assert after.business_value_hash == before.business_value_hash
        assert after.canvas_hash == before.canvas_hash
        assert hardened.metadata["candidate_generation"]["generation_version"] == "candidate_generation_v3_category_hardened"
        documents[variant.variant_id] = hardened
    diversity = category_group_diversity(documents)
    assert diversity["distinct_layout_family_count"] == 4
    assert diversity["passes"] is True


def test_category_quality_floor_rejects_named_aesthetic_failures() -> None:
    source, _ = _design("sale")
    hardened = apply_category_hardening_v2(source, variants_for_category_v2("sale")[0])
    passed = evaluate_category_quality_floor_v2(hardened, {"coverage": .5, "outside_canvas_rate": 0, "overlap_ratio": 0, "text_fit_rate": 1, "text_overflow_count": 0})
    assert passed.passed is True
    broken = hardened.model_copy(deep=True)
    broken.elements = [
        element
        for element in broken.elements
        if str(element.metadata.get("asset_role")) != "product"
    ]
    failed = evaluate_category_quality_floor_v2(broken, {"coverage": .05, "outside_canvas_rate": .1, "overlap_ratio": .2, "text_fit_rate": .5, "text_overflow_count": 1})
    assert failed.passed is False
    assert "TECHNICAL_FAILURE" in failed.reasons
    assert "EXCESSIVE_UNUSED_SPACE" in failed.reasons


def test_phase1_2_queue_provenance_is_isolated_and_both_bad_has_no_winner() -> None:
    candidates = [
        CandidateArtifactV1(
            design_id=f"pilot_v3:sale:{index}",
            brief_id="sale_pilot",
            design_path=f"design_{index}.json",
            preview_path=f"preview_{index}.png",
            content_sha256=f"{index:x}" * 64,
            generation_source="fixture",
            technically_eligible=True,
            provenance={"generation_version": "candidate_generation_v3_category_hardened"},
            license_class="research_only",
            commercial_allowed=False,
        )
        for index in range(1, 5)
    ]
    pairs = tournament_pairs(
        brief_id="sale_pilot",
        prompt="MEGA SALE",
        category="sale",
        candidates=candidates,
        benchmark_sample_data=True,
        customer_provided=False,
        provenance={"queue_id": "v04_phase1_2_category_pilot", "generation_version": "candidate_generation_v3_category_hardened", "quality_floor_passed": True},
    )
    assert len(pairs) == 4
    assert all(item.provenance["queue_id"] == "v04_phase1_2_category_pilot" for item in pairs)
    review = _review(90, session_id="session:" + "9" * 24, category="sale", choice="both_bad", generation_version="candidate_generation_v3_category_hardened")
    assert review.choice == "both_bad"
    assert not hasattr(review, "chosen_design_id")


def test_phase1_2_review_queue_alias_is_isolated() -> None:
    resolved = resolve_queue_path("v04_phase1_2_category_pilot")
    assert str(resolved).replace("\\", "/").endswith(
        "v0_4_phase1_2_category_hardening/review_queue/review_queue.jsonl"
    )
    assert "phase1_1" not in str(resolved)
