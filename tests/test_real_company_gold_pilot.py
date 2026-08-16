from __future__ import annotations

from training.company_archive.gold_pilot import (
    assess_roundtrip_support,
    extract_gold_candidate_grammar,
    extraction_coverage,
    infer_semantic_roles,
)
from training.company_archive.models import CdrInspectionV1, CdrObjectV1
from training.company_archive.extractor import inspection_to_design_document


SOURCE_SHA = "a" * 64


def _document():
    inspection = CdrInspectionV1(
        source_path="C:/private/source.cdr",
        source_size_bytes=100,
        source_mtime_ns=123,
        corel_version="Version 22.0.0.412",
        page_count=1,
        page_width=200,
        page_height=100,
        unit="mm",
        corel_unit_code=3,
        layer_count=1,
        object_count=2,
        text_object_count=1,
        bitmap_count=0,
        vector_count=1,
        group_count=0,
        objects=[
            CdrObjectV1(
                object_id="headline",
                corel_name="Text 1",
                object_type="text",
                bbox={"x": 10, "y": 10, "width": 100, "height": 20},
                bbox_norm={"x": 0.05, "y": 0.1, "width": 0.5, "height": 0.2},
                text="REAL HEADLINE",
                font_family="Arial",
                font_size=28,
            ),
            CdrObjectV1(
                object_id="curve",
                corel_name="Curve 1",
                object_type="vector",
                bbox={"x": 20, "y": 40, "width": 80, "height": 30},
                bbox_norm={"x": 0.1, "y": 0.4, "width": 0.4, "height": 0.3},
            ),
        ],
    )
    return inspection_to_design_document(
        inspection,
        source_sha256=SOURCE_SHA,
        category="OTHER",
    )


def test_company_candidate_grammar_is_fail_closed_and_semantics_are_explicit():
    document = _document()
    mapping, evidence = infer_semantic_roles(document)
    assert mapping["headline"] == "HEADLINE"
    assert mapping["curve"] == "UNKNOWN"
    assert all(item["human_labeled"] is False for item in evidence)

    grammar, report = extract_gold_candidate_grammar(
        document,
        design_id="CDR_000001",
        source_sha256=SOURCE_SHA,
    )
    assert grammar.gold_status == "PROVISIONAL_REAL_REFERENCE"
    assert grammar.provenance["human_certified_gold"] is False
    assert grammar.provenance["commercial_allowed"] is False
    assert grammar.provenance["project_owned"] is False
    assert report["human_labeled_semantic_count"] == 0


def test_company_candidate_roundtrip_reports_unsupported_vector():
    document = _document()
    coverage = extraction_coverage(document)
    assert coverage["extracted_object_count"] == 2
    assert coverage["reconstructable_object_count"] == 1
    assert coverage["normalized_bbox_valid"] is True

    roundtrip = assess_roundtrip_support(document)
    assert roundtrip["status"] == "ROUNDTRIP_BAD"
    assert roundtrip["control_executed_in_corel"] is False
    assert "not supported" in roundtrip["error"]


def test_company_candidate_rejects_owned_or_commercial_metadata():
    document = _document()
    document.metadata["project_owned"] = True
    try:
        extract_gold_candidate_grammar(
            document,
            design_id="CDR_000001",
            source_sha256=SOURCE_SHA,
        )
    except ValueError as exc:
        assert "cannot widen" in str(exc)
    else:  # pragma: no cover - explicit fail-closed guard
        raise AssertionError("owned candidate metadata was accepted")
