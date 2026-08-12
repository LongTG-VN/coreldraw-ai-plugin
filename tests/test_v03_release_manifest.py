from __future__ import annotations

import json
from pathlib import Path


def test_v03_release_manifest_is_explicitly_research_only() -> None:
    path = Path("training/config/releases/design_ai_v0_3.json")
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["release"]["version"] == "0.3"
    assert payload["release"]["status"] == "verified_clean_research_checkpoint"
    assert payload["release"]["production_ready"] is False
    assert payload["release"]["commercial_allowed"] is False
    assert payload["reference_corpus"]["research_only"] is True
    assert payload["clean_validation"]["fresh_candidate_count"] == 52
    assert payload["clean_validation"]["reused_candidate_count"] == 0
    assert payload["clean_validation"]["strict_schema_valid_count"] == 52
    assert payload["clean_validation"]["raw_schema_valid_count"] == 0
    assert payload["acceptance"]["v0.3_complete"] is True
    assert payload["acceptance"]["ready_for_v0.4_preference_training"] is False
    assert payload["runtime_surface"]["fastapi_design_generate"] == "baseline_only"
