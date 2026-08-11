from __future__ import annotations

import pytest
from pydantic import ValidationError

from training.adapters.base import AdapterError
from training.adapters.internal_cdr import InternalCdrAdapter, InternalCdrExportBundleV1
from training.evaluation.ablation import ABLATION_VARIANTS, aggregate_ablation_rows


def _metrics(value: float) -> dict[str, float]:
    return {
        "combined": value,
        "technical": value,
        "overlap": 1 - value,
        "spacing": value,
        "hierarchy": value,
        "text_fit": value,
        "coverage": value,
    }


def test_ablation_aggregation_keeps_stage_identity() -> None:
    rows = [
        {
            "variants": {
                variant: {
                    "strict_schema_valid": True,
                    "corel_compile_success": True,
                    "preview_exists": True,
                    "metrics": _metrics(.5 + index * .2),
                }
                for index, variant in enumerate(ABLATION_VARIANTS)
            }
        }
    ]

    report = aggregate_ablation_rows(rows)

    assert list(report) == list(ABLATION_VARIANTS)
    assert report["rag_recovery_only"]["metrics"]["combined"] == .5
    assert report["rag_reference_layout_typography"]["metrics"]["combined"] == .7
    assert report["rag_reference_visual_full"]["metrics"]["combined"] == .9
    assert report["rag_reference_visual_full"]["corel_compile_success"] == 1
    with pytest.raises(ValueError, match="at least one"):
        aggregate_ablation_rows([])


def _bundle() -> dict:
    return {
        "schema_version": "1.0",
        "bundle_id": "approved-project-001",
        "cdr_path": "exports/project.cdr",
        "preview_path": "exports/project.png",
        "design_document_path": "exports/project.design.json",
        "category": "spa",
        "assets": [
            {
                "asset_id": "hero-1",
                "source_path": "assets/hero.png",
                "asset_type": "bitmap",
                "license_class": "company_owned",
                "commercial_allowed": True,
            }
        ],
        "font_families": ["Arial"],
        "colors": ["#F5EBDD", "#C49A52"],
        "z_order": ["background", "hero", "headline"],
        "project_metadata": {"customer_id_removed": True},
        "version_history": [
            {
                "version_id": "v1",
                "created_at": "2026-08-12T00:00:00Z",
                "design_document_path": "versions/v1.design.json",
                "preview_path": "versions/v1.png",
            }
        ],
        "license_class": "company_owned",
        "commercial_allowed": True,
        "approved_for_training": True,
    }


def test_internal_cdr_future_contract_validates_but_ingestion_stays_disabled() -> None:
    adapter = InternalCdrAdapter()
    bundle = adapter.validate_export_bundle(_bundle())

    assert isinstance(bundle, InternalCdrExportBundleV1)
    assert bundle.approved_for_training is True
    with pytest.raises(AdapterError, match="disabled"):
        adapter.convert(_bundle(), 0)


def test_internal_cdr_contract_rejects_unverified_training_rights() -> None:
    payload = _bundle()
    payload["commercial_allowed"] = False

    with pytest.raises(ValidationError, match="commercial rights"):
        InternalCdrExportBundleV1.model_validate(payload)
