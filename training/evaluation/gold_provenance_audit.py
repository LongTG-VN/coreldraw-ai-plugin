"""Gold Design Grammar Provenance Audit tool."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from training.gold.library import get_gold_library


GOLD_PILOT_ROOT = Path("training/artifacts/benchmarks/20260812_gold_design_grammar_pilot")


def run_gold_provenance_audit(
    output_root: Path = GOLD_PILOT_ROOT,
) -> dict[str, Any]:
    """Audit the provenance of all 15 provisional Gold grammars in the library."""

    audit_dir = output_root / "audit"
    audit_dir.mkdir(parents=True, exist_ok=True)

    library = get_gold_library()
    grammar_audits: list[dict[str, Any]] = []

    real_extracted_count = 0
    manually_authored_count = 0

    for g in library:
        # Check whether an underlying source design file exists on disk
        extracted_from_real = False
        source_ref = g.provenance.get("extracted_from_sample_id")

        if source_ref and Path(str(source_ref)).exists():
            extracted_from_real = True
            classification = "REAL_REFERENCE_EXTRACTED"
            real_extracted_count += 1
        else:
            classification = "MANUALLY_AUTHORED_GRAMMAR"
            manually_authored_count += 1

        audit_entry = {
            "grammar_id": g.grammar_id,
            "grammar_name": g.grammar_name,
            "category": g.category,
            "source_reference": source_ref or "None (Authored in training/gold/library.py)",
            "source_file_path": None,
            "source_artifact_hash": None,
            "source_type": "manually_authored_python_structure" if not extracted_from_real else "project_owned_design",
            "classification": classification,
            "extracted_from_real_design": extracted_from_real,
            "exact_license": "UNKNOWN",
            "commercial_allowed": False,
            "extraction_method": "manual_python_authoring" if not extracted_from_real else "GoldGrammarExtractor",
            "extractor_used": None if not extracted_from_real else "GoldGrammarExtractor",
            "extraction_timestamp": None,
            "source_design_document_available": False,
            "source_preview_available": False,
            "human_certified": False,
        }
        grammar_audits.append(audit_entry)

    total_count = len(library)
    real_rate = (real_extracted_count / total_count) if total_count > 0 else 0.0

    if real_extracted_count == total_count:
        conclusion = "GOLD_REFERENCE_PIPELINE_VALID"
    elif manually_authored_count == total_count:
        conclusion = "GRAMMARS_ARE_MANUALLY_AUTHORED_TEMPLATES"
    elif real_extracted_count > 0:
        conclusion = "MIXED_GOLD_PROVENANCE"
    else:
        conclusion = "GOLD_PROVENANCE_INCONCLUSIVE"

    report = {
        "schema_version": "1.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "milestone": "v0.4 Phase 1.3 — Gold Design Grammar",
        "conclusion": conclusion,
        "relabeled_milestone_status": "STRUCTURED_GRAMMAR_ADAPTATION_PILOT",
        "tested_hypothesis": "Hypothesis B: Manually Authored Template -> Adaptation",
        "total_grammars_audited": total_count,
        "real_reference_extracted_count": real_extracted_count,
        "manually_authored_count": manually_authored_count,
        "unknown_count": 0,
        "real_reference_extracted_rate": real_rate,
        "grammars": grammar_audits,
    }

    with open(audit_dir / "GOLD_PROVENANCE_AUDIT.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    return report
