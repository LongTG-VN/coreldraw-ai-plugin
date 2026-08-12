"""Regression guards for research-integrity failures found during stabilization."""

from __future__ import annotations

from pathlib import Path

from training.gold.real_pipeline import (
    GENPOSTER_COMMERCIAL_ALLOWED,
    GENPOSTER_LICENSE_CLASS,
    GENPOSTER_PROJECT_OWNED,
)
from training.schemas.gold import GoldDesignGrammarV1


RESEARCH_RUNNERS = (
    Path("training/evaluation/gold_grammar_pilot.py"),
    Path("training/evaluation/real_gold_pilot.py"),
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


def test_research_runners_never_write_fake_cdr_magic_headers():
    forbidden_markers = (
        "GOLD_GRAMMAR_CDR_HEADER_",
        "REAL_GOLD_CDR_HEADER_",
    )
    for runner in RESEARCH_RUNNERS:
        source = runner.read_text(encoding="utf-8")
        for marker in forbidden_markers:
            assert marker not in source, f"fake CDR marker reintroduced in {runner}: {marker}"


def test_research_runners_require_real_corel_for_cdr_claims():
    for runner in RESEARCH_RUNNERS:
        source = runner.read_text(encoding="utf-8")
        assert "NOT_GENERATED_REQUIRES_REAL_COREL_API" in source
        assert "real_cdr_verified" in source
