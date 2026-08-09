from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

from training.tools.bootstrap import build_plan, load_registry
from training.tools.preflight import build_report, recommend_mode
from training.tools.probe_dataset import summarize_row


REPO_ROOT = Path(__file__).resolve().parents[1]


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


def test_preflight_report_includes_resource_and_cuda_provenance() -> None:
    report = build_report()

    assert report["cpu"]["logical_cores"]
    assert report["ram"]["total_gb"]
    assert "driver_reported_version" in report["cuda"]
    assert "toolkit_available" in report["cuda"]


def test_genposter_probe_summary_does_not_serialize_full_images() -> None:
    row = {
        "id": 7,
        "background_image": SimpleNamespace(size=(1080, 1350)),
        "regions": [[0, 0, 10, 10]],
        "psd_path": "sample.psd",
        "layers": {
            "text": ["TITLE", "Subtitle"],
            "bbox": [[10, 20, 100, 50], [20, 80, 120, 40]],
            "psd_size": [[1080, 1350], [1080, 1350]],
        },
    }

    summary = summarize_row("genposter100k", row, 0)

    assert summary["upstream_id"] == 7
    assert summary["canvas_size"] == [1080, 1350]
    assert summary["layer_count"] == 2
    assert summary["sample_texts"] == ["TITLE", "Subtitle"]
    assert "background_image" not in summary


def test_probe_tool_supports_documented_direct_invocation() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "training" / "tools" / "probe_dataset.py"),
            "--help",
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert "Stream a tiny public dataset subset" in completed.stdout
