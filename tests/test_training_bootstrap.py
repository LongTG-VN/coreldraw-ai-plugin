from __future__ import annotations

from types import SimpleNamespace

from training.tools.bootstrap import build_plan, load_registry
from training.tools.preflight import recommend_mode
from training.tools.probe_dataset import summarize_row


def test_dataset_registry_keeps_research_sources_noncommercial() -> None:
    registry = load_registry()

    genposter = registry["sources"]["genposter100k"]
    cgl = registry["sources"]["cgl_v2"]
    synthetic = registry["sources"]["synthetic_owned"]

    assert genposter["commercial_allowed"] is False
    assert genposter["license_class"] == "research_only"
    assert cgl["commercial_allowed"] is False
    assert cgl["license_class"] == "research_only_unverified"
    assert synthetic["commercial_allowed"] is True


def test_smoke_plan_is_bounded_and_does_not_download_data() -> None:
    plan = build_plan("smoke", clone_upstreams=False)

    assert plan["max_samples"] == 500
    assert plan["dataset_downloads"] == "none"
    assert plan["upstreams"] == {}
    assert any(path.endswith("training/data/research") for path in plan["directories"])


def test_preflight_gpu_recommendation() -> None:
    assert recommend_mode([]) == "pipeline_and_dataset_first"
    assert (
        recommend_mode([{"memory_mb": 16 * 1024}])
        == "small_model_or_aggressive_qlora"
    )
    assert recommend_mode([{"memory_mb": 24 * 1024}]) == "lora_7b_candidate"


def test_genposter_probe_summary_does_not_serialize_full_images() -> None:
    row = {
        "id": 7,
        "background_image": SimpleNamespace(size=(1080, 1350)),
        "regions": [[0, 0, 10, 10]],
        "psd_path": "sample.psd",
        "layers": {
            "text": ["TITLE", "Subtitle"],
            "bbox": [[10, 20, 100, 50], [20, 80, 120, 40]],
        },
    }

    summary = summarize_row("genposter100k", row, 0)

    assert summary["upstream_id"] == 7
    assert summary["canvas_size"] == [1080, 1350]
    assert summary["layer_count"] == 2
    assert summary["sample_texts"] == ["TITLE", "Subtitle"]
    assert "background_image" not in summary
