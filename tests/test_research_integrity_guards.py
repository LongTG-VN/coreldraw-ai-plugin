"""Regression guards for research-integrity failures found during stabilization."""

from __future__ import annotations

from pathlib import Path

from training.gold.real_pipeline import (
    GENPOSTER_COMMERCIAL_ALLOWED,
    GENPOSTER_LICENSE_CLASS,
    GENPOSTER_PROJECT_OWNED,
)
from training.schemas.gold import GoldDesignGrammarV1


CDR_RESEARCH_RUNNERS = (
    Path("training/evaluation/gold_grammar_pilot.py"),
    Path("training/evaluation/real_gold_pilot.py"),
    Path("training/evaluation/real_planner_audit.py"),
)


def test_genposter_rights_are_fail_closed():
    assert GENPOSTER_LICENSE_CLASS == "CC-BY-NC-4.0"
    assert GENPOSTER_COMMERCIAL_ALLOWED is False
    assert GENPOSTER_PROJECT_OWNED is False


def test_unbound_gold_grammar_defaults_are_not_commercial():
    grammar = GoldDesignGrammarV1(
        grammar_id="guard",
        grammar_name="Guard",
        category="TEST",
        canvas_aspect_ratio=1.0,
        slots=[],
    )
    assert grammar.provenance["license_class"] == "UNKNOWN"
    assert grammar.provenance["commercial_allowed"] is False
    assert grammar.provenance["project_owned"] is False


def test_research_runners_never_write_known_fake_cdr_magic_headers():
    forbidden_markers = (
        "GOLD_GRAMMAR_CDR_HEADER_",
        "REAL_GOLD_CDR_HEADER_",
        "REAL_PLANNER_PILOT_CDR_",
    )
    for runner in CDR_RESEARCH_RUNNERS:
        source = runner.read_text(encoding="utf-8")
        for marker in forbidden_markers:
            assert marker not in source, f"fake CDR marker reintroduced in {runner}: {marker}"


def test_gold_research_runners_require_real_corel_for_cdr_claims():
    for runner in CDR_RESEARCH_RUNNERS[:2]:
        source = runner.read_text(encoding="utf-8")
        assert "NOT_GENERATED_REQUIRES_REAL_COREL_API" in source
        assert "real_cdr_verified" in source


def test_real_planner_shootout_is_fail_closed():
    source = Path("training/evaluation/real_planner_audit.py").read_text(encoding="utf-8")
    assert 'execute: bool = False' in source
    assert '"PLANNER_SHOOTOUT_FROZEN"' in source
    assert '"design_plan_derived_from_ai_output"' in source
    assert '"external_execution_verified"' in source
    assert 'review_queue.jsonl' not in source
    assert 'output.cdr' not in source
