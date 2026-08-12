from __future__ import annotations

import json
from pathlib import Path


def test_v031_release_manifest_is_honest_and_pinned() -> None:
    payload = json.loads(
        Path("training/config/releases/design_ai_v0_3_1.json").read_text(encoding="utf-8")
    )

    release = payload["release"]
    validation = payload["clean_validation"]
    acceptance = payload["acceptance"]
    assert release["version"] == "0.3.1"
    assert release["production_ready"] is False
    assert release["commercial_allowed"] is False
    assert release["human_reviewed"] is False
    assert release["research_only"] is True
    assert payload["model"]["model_revision"] == (
        "70d244cc86ccca08cf5af4e1e306ecf908b1ad5e"
    )
    assert payload["model"]["retrained_for_v0.3.1"] is False
    assert validation["fresh_candidate_count"] == 52
    assert validation["resumed_verified_candidate_count"] == 0
    assert validation["audited_raw_cache_reuse_count"] == 0
    assert validation["unsafe_reused_candidate_count"] == 0
    assert validation["strict_schema_valid_count"] == 52
    assert validation["raw_schema_valid_count"] == 0
    assert validation["winner_unresolved_overflow_count"] == 0
    assert validation["rejected_candidate_unresolved_overflow_count"] == 15
    assert payload["dense_menu"]["fake_customer_prices"] is False
    assert payload["dense_menu"]["item_placeholder_count"] == 10
    assert payload["dense_menu"]["price_placeholder_count"] == 10
    assert acceptance["v0.3.1_complete"] is True
    assert acceptance["ready_for_human_review"] is True
    assert acceptance["ready_for_v0.4_preference_training"] is False
    assert acceptance["production_ready"] is False
    assert acceptance["commercial_allowed"] is False
