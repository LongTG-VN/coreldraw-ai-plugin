"""Fail-closed helpers for the real company Gold-grammar candidate pilot.

This module does not certify Gold, widen company rights, or conceal unsupported
Corel object types.  It exists to bind a real archive CDR extraction to a
provisional grammar and to decide whether the current deterministic Corel
compiler can perform a meaningful control round trip.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from typing import Any

from training.gold.extractor import GoldGrammarExtractor
from training.inference.corel_compiler import CorelCompileError, compile_corel_operations
from training.schemas.design import DesignDocument, DesignElement
from training.schemas.gold import GoldDesignGrammarV1, SemanticRole


PILOT_EXTRACTOR_VERSION = "real_company_gold_candidate_v1"
SEMANTIC_ASSIGNMENT_METHOD = "deterministic_text_and_geometry_heuristics_v1"


def canonical_sha256(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _text_role(element: DesignElement, *, largest_text_id: str | None) -> tuple[SemanticRole, float, str]:
    content = element.text.content.strip() if element.text else ""
    lowered = content.casefold()
    if re.search(r"(?:\+?84|0)\s*\d(?:[ .-]*\d){7,10}", content):
        return "CONTACT", 0.9, "phone_pattern"
    if any(token in lowered for token in ("địa chỉ", "dia chi", "address")):
        return "ADDRESS", 0.85, "address_keyword"
    if re.search(r"(?:\d[\d., ]*)\s*(?:đ|vnd|k)\b", lowered):
        return "PRICE", 0.82, "price_pattern"
    if any(token in lowered for token in ("giảm", "sale", "khuyến mãi", "ưu đãi", "%")):
        return "OFFER", 0.8, "offer_keyword"
    if any(token in lowered for token in ("liên hệ", "đặt ngay", "mua ngay", "gọi ngay")):
        return "CTA", 0.78, "cta_keyword"
    if re.search(r"\b\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?\b", content):
        return "DATE", 0.75, "date_pattern"
    if element.id == largest_text_id:
        return "HEADLINE", 0.68, "largest_text_font"
    return "BODY", 0.45, "unclassified_text"


def infer_semantic_roles(
    document: DesignDocument,
) -> tuple[dict[str, SemanticRole], list[dict[str, Any]]]:
    """Assign bounded heuristic roles while preserving explicit uncertainty."""

    text_elements = [
        element
        for element in document.elements
        if element.type == "text" and element.text is not None
    ]
    largest_text = max(
        text_elements,
        key=lambda element: float(element.text.font_size or 0.0),
        default=None,
    )
    mapping: dict[str, SemanticRole] = {}
    evidence: list[dict[str, Any]] = []
    for element in document.elements:
        if element.type == "text":
            role, confidence, reason = _text_role(
                element,
                largest_text_id=largest_text.id if largest_text else None,
            )
        elif element.metadata.get("source_object_type") == "image":
            area = float(element.bbox_norm.width * element.bbox_norm.height)
            if area >= 0.15:
                role, confidence, reason = "HERO", 0.55, "large_bitmap_region"
            else:
                role, confidence, reason = "UNKNOWN", 0.2, "bitmap_semantics_unknown"
        elif (
            element.type == "rectangle"
            and float(element.bbox_norm.width * element.bbox_norm.height) >= 0.8
        ):
            role, confidence, reason = "BACKGROUND", 0.7, "page_covering_rectangle"
        elif element.type in {"rectangle", "ellipse"}:
            role, confidence, reason = "DECORATION", 0.5, "simple_vector_shape"
        else:
            role, confidence, reason = "UNKNOWN", 0.1, "unsupported_semantics"
        mapping[element.id] = role
        evidence.append(
            {
                "element_id": element.id,
                "role": role,
                "confidence": confidence,
                "reason": reason,
                "human_labeled": False,
            }
        )
    return mapping, evidence


def extract_gold_candidate_grammar(
    document: DesignDocument,
    *,
    design_id: str,
    source_sha256: str,
) -> tuple[GoldDesignGrammarV1, dict[str, Any]]:
    """Extract a provisional candidate grammar without bypassing human Gold gates."""

    if not re.fullmatch(r"[a-f0-9]{64}", source_sha256):
        raise ValueError("candidate grammar requires a full source SHA256")
    if document.metadata.get("source_type") != "COMPANY_ARCHIVE_CDR":
        raise ValueError("candidate pilot requires an unowned company archive CDR source")
    if document.source.upstream_id != source_sha256:
        raise ValueError("DesignDocument SHA256 provenance does not match source")
    if document.source.commercial_allowed or document.metadata.get("project_owned") is True:
        raise ValueError("candidate pilot cannot widen source rights")

    role_mapping, assignments = infer_semantic_roles(document)
    grammar = GoldGrammarExtractor().extract(
        document,
        grammar_id=f"company_candidate_{design_id.casefold()}",
        grammar_name=f"Real company candidate {design_id}",
        role_mapping=role_mapping,
    )
    grammar.gold_status = "PROVISIONAL_REAL_REFERENCE"
    document_hash = canonical_sha256(document.model_dump(mode="json"))
    grammar.provenance.update(
        {
            "source_type": "COMPANY_ARCHIVE_CDR",
            "source_design_id": design_id,
            "source_sha256": source_sha256,
            "design_document_hash": document_hash,
            "extractor_version": PILOT_EXTRACTOR_VERSION,
            "human_quality_status": "GOLD_CANDIDATE_FINAL",
            "human_certified_gold": False,
            "commercial_allowed": False,
            "project_owned": False,
            "rights_status": "UNKNOWN",
            "semantic_assignment_method": SEMANTIC_ASSIGNMENT_METHOD,
            "semantic_assignments": assignments,
            "semantic_roles_are_human_labels": False,
        }
    )
    report = {
        "design_id": design_id,
        "source_sha256": source_sha256,
        "design_document_hash": document_hash,
        "grammar_hash": canonical_sha256(grammar.model_dump(mode="json")),
        "extractor_version": PILOT_EXTRACTOR_VERSION,
        "semantic_assignment_method": SEMANTIC_ASSIGNMENT_METHOD,
        "semantic_role_counts": dict(Counter(role_mapping.values())),
        "semantic_assignment_count": len(assignments),
        "human_labeled_semantic_count": 0,
    }
    return grammar, report


def extraction_coverage(document: DesignDocument) -> dict[str, Any]:
    source_types = Counter(
        str(element.metadata.get("source_object_type") or element.type)
        for element in document.elements
    )
    reconstructable = sum(
        bool(element.metadata.get("reconstructable_by_current_compiler"))
        for element in document.elements
    )
    text_elements = [element for element in document.elements if element.type == "text"]
    font_covered = sum(
        bool(element.text and element.text.font_family) for element in text_elements
    )
    return {
        "extracted_object_count": len(document.elements),
        "source_object_type_counts": dict(source_types),
        "reconstructable_object_count": reconstructable,
        "reconstructable_object_rate": reconstructable / len(document.elements)
        if document.elements
        else 1.0,
        "font_metadata_coverage": font_covered / len(text_elements)
        if text_elements
        else None,
        "normalized_bbox_valid": all(
            0.0 <= float(element.bbox_norm.x) <= 1.0
            and 0.0 <= float(element.bbox_norm.y) <= 1.0
            and 0.0 < float(element.bbox_norm.width) <= 1.0
            and 0.0 < float(element.bbox_norm.height) <= 1.0
            and float(element.bbox_norm.x + element.bbox_norm.width) <= 1.000001
            and float(element.bbox_norm.y + element.bbox_norm.height) <= 1.000001
            for element in document.elements
        ),
    }


def assess_roundtrip_support(document: DesignDocument) -> dict[str, Any]:
    """Compile a control request or fail with explicit negative evidence."""

    try:
        operations = compile_corel_operations(document)
    except CorelCompileError as exc:
        return {
            "status": "ROUNDTRIP_BAD",
            "control_compiled": False,
            "control_executed_in_corel": False,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "operation_count": None,
        }
    return {
        "status": "ROUNDTRIP_COMPILE_READY",
        "control_compiled": True,
        "control_executed_in_corel": False,
        "error_type": None,
        "error": None,
        "operation_count": len(operations),
        "operations": operations,
    }


__all__ = [
    "PILOT_EXTRACTOR_VERSION",
    "SEMANTIC_ASSIGNMENT_METHOD",
    "assess_roundtrip_support",
    "canonical_sha256",
    "extract_gold_candidate_grammar",
    "extraction_coverage",
    "infer_semantic_roles",
]
