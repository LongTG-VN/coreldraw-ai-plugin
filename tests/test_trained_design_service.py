from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

import main
from training.inference.qwen3_planner import RawPlannerGeneration
from training.inference.service import (
    MODEL_ID,
    MODEL_REVISION,
    TrainedDesignRequest,
    TrainedDesignService,
    TrainedDesignServiceConfig,
    TrainedDesignUnavailableError,
)
from training.retrieval import (
    ReferenceMetadataV1,
    ReferenceRecordV1,
    extract_reference_features,
    summarize_reference,
)
from training.tools.build_reference_corpus import _generic_document


class FakeTokenizer:
    def apply_chat_template(self, messages, **kwargs):  # type: ignore[no-untyped-def]
        return "\n".join(item["content"] for item in messages)

    def __call__(self, value, **kwargs):  # type: ignore[no-untyped-def]
        return {"input_ids": value.split()}


class FakeSession:
    load_duration_seconds = 0.012

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.tokenizer = FakeTokenizer()
        self.calls = 0

    def generate_raw(self, **kwargs: Any) -> RawPlannerGeneration:
        self.calls += 1
        payload = {
            "canvas": {
                "width": kwargs["width_mm"],
                "height": kwargs["height_mm"],
                "unit": "mm",
            },
            "category": "spa",
            "elements": [
                {
                    "type": "text",
                    "name": "Headline",
                    "role": "headline",
                    "text": "AN NHIÊN SPA",
                    "position": {"x": 20, "y": 15},
                    "size": {"width": 180, "height": 25},
                    "font_size": 24,
                },
                {
                    "type": "text",
                    "name": "CTA",
                    "role": "cta",
                    "text": "Đặt lịch",
                    "position": {"x": 20, "y": 85},
                    "size": {"width": 90, "height": 18},
                    "font_size": 12,
                },
            ],
        }
        return RawPlannerGeneration(
            raw_output=json.dumps(payload, ensure_ascii=False),
            duration_seconds=0.02,
            seed=int(kwargs["seed"]),
            generation_config={"max_new_tokens": kwargs["max_new_tokens"]},
            peak_vram_gib=0.4,
        )


def _reference_record(tmp_path: Path) -> ReferenceRecordV1:
    document = _generic_document("spa", "hero_right", ["cream", "gold"])
    features = extract_reference_features(document)
    metadata = ReferenceMetadataV1(
        reference_id="fixture:spa:hero_right",
        category="spa",
        format="poster",
        aspect_ratio=float(features.aspect_ratio),
        style_tags=["luxury", "minimal"],
        color_tags=["cream", "gold"],
        text_density=features.text_density,
        element_count=features.element_count,
        layout_features={"composition": features.composition},
        design_document_path=str(tmp_path / "reference.json"),
        preview_path=str(tmp_path / "reference.png"),
        source="synthetic_owned",
        license="project_owned",
        license_class="production_safe",
        research_only=False,
        commercial_allowed=True,
    )
    return ReferenceRecordV1(
        metadata=metadata,
        features=features,
        summary=summarize_reference(metadata, features),
    )


def _config(tmp_path: Path, *, checkpoint_exists: bool = True) -> TrainedDesignServiceConfig:
    checkpoint = tmp_path / "checkpoint-5"
    if checkpoint_exists:
        checkpoint.mkdir()
        (checkpoint / "adapter_config.json").write_text("{}\n", encoding="utf-8")
    reference_index = tmp_path / "reference_index.jsonl"
    reference_index.write_text(
        _reference_record(tmp_path).model_dump_json() + "\n",
        encoding="utf-8",
    )
    model_config = tmp_path / "model.json"
    model_config.write_text(
        json.dumps(
            {
                "model_id": MODEL_ID,
                "model_revision": MODEL_REVISION,
                "lora": {"rank": 8, "alpha": 16},
            }
        ),
        encoding="utf-8",
    )
    score_config = tmp_path / "score.json"
    score_config.write_text(
        json.dumps(
            {
                "weights": {
                    "technical": 0.25,
                    "composition": 0.15,
                    "visual_hierarchy": 0.15,
                    "typography": 0.10,
                    "spacing": 0.10,
                    "color_harmony": 0.08,
                    "balance": 0.05,
                    "readability": 0.10,
                    "prompt_match": 0.02,
                }
            }
        ),
        encoding="utf-8",
    )
    return TrainedDesignServiceConfig(
        repo_root=tmp_path,
        checkpoint=checkpoint,
        reference_index=reference_index,
        model_config=model_config,
        score_config=score_config,
        artifact_root=tmp_path / "runtime",
        context_token_budget=350,
        max_new_tokens=256,
    )


def test_status_is_lazy_and_does_not_construct_session(tmp_path: Path) -> None:
    calls = 0

    def factory(**kwargs: Any) -> FakeSession:
        nonlocal calls
        calls += 1
        return FakeSession(**kwargs)

    service = TrainedDesignService(_config(tmp_path), session_factory=factory)
    first = service.status()
    second = service.status()

    assert calls == 0
    assert first.available is True
    assert first.loaded is False
    assert second.generation_count == 0
    assert first.model_id == MODEL_ID
    assert first.revision == MODEL_REVISION


def test_visual_runtime_status_is_lazy_and_independent_from_planner(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    visual_index = tmp_path / "visual-index"
    visual_index.mkdir()
    (visual_index / "index_manifest.json").write_text("{}\n", encoding="utf-8")
    visual_config = tmp_path / "visual-config.json"
    visual_config.write_text(
        json.dumps(
            {
                "embedding": {
                    "model_id": "fixture/visual",
                    "revision": "fixture-revision",
                },
                "weights": {
                    "structural": .45,
                    "visual_text": .40,
                    "visual_asset": .15,
                },
                "mmr_lambda": .70,
            }
        ),
        encoding="utf-8",
    )
    calls = 0

    def visual_factory(**kwargs: Any) -> Any:
        nonlocal calls
        calls += 1
        raise AssertionError(f"visual model must remain lazy: {kwargs}")

    service = TrainedDesignService(
        config.__class__(
            **{
                **config.__dict__,
                "visual_index": visual_index,
                "visual_config": visual_config,
                "visual_enabled": True,
            }
        ),
        session_factory=FakeSession,
        visual_embedder_factory=visual_factory,
    )

    status = service.status()

    assert calls == 0
    assert status.planner_model["loaded"] is False
    assert status.visual_embedding_model["configured"] is True
    assert status.visual_embedding_model["loaded"] is False
    assert status.structural_index["available"] is True
    assert status.visual_index["available"] is True


def test_failed_visual_rag_requires_explicit_environment_opt_in(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("DESIGN_AI_VISUAL_RAG_ENABLED", raising=False)
    config = TrainedDesignServiceConfig.from_environment(tmp_path)
    assert config.visual_enabled is False

    monkeypatch.setenv("DESIGN_AI_VISUAL_RAG_ENABLED", "true")
    opted_in = TrainedDesignServiceConfig.from_environment(tmp_path)
    assert opted_in.visual_enabled is True


def test_service_loads_once_reuses_session_and_writes_manifest(tmp_path: Path) -> None:
    sessions: list[FakeSession] = []

    def factory(**kwargs: Any) -> FakeSession:
        session = FakeSession(**kwargs)
        sessions.append(session)
        return session

    service = TrainedDesignService(_config(tmp_path), session_factory=factory)
    request = TrainedDesignRequest(
        prompt="Poster spa cao cấp màu kem và vàng",
        width_mm=210,
        height_mm=120,
        num_candidates=1,
        seed=42,
        reference_top_k=1,
    )
    first = service.generate(request)
    second = service.generate(request.model_copy(update={"seed": 43}))

    assert len(sessions) == 1
    assert sessions[0].calls == 2
    assert service.status().loaded is True
    assert service.status().generation_count == 2
    assert first.design.metadata["trained_model"] is True
    assert first.research_only is True
    assert first.commercial_allowed is False
    assert first.references[0]["reference_id"] == "fixture:spa:hero_right"
    assert first.corel_operations[0]["op"] == "page_resize"
    manifest_path = Path(first.generation_metadata["artifact_path"]) / "run_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["run_id"] == first.run_id
    assert manifest["model_revision"] == MODEL_REVISION
    assert manifest["visual_engine_version"] == "visual_composition_v0.3.1"
    assert manifest["commercial_allowed"] is False
    assert second.run_id != first.run_id


def test_missing_checkpoint_is_explicitly_unavailable_without_loading(tmp_path: Path) -> None:
    service = TrainedDesignService(
        _config(tmp_path, checkpoint_exists=False),
        session_factory=lambda **_: pytest.fail("session must not load"),
    )

    assert service.status().available is False
    assert service.status().checkpoint_exists is False
    with pytest.raises(TrainedDesignUnavailableError, match="checkpoint missing"):
        service.generate(
            TrainedDesignRequest(
                prompt="Poster spa",
                width_mm=210,
                height_mm=297,
                num_candidates=1,
            )
        )


def test_trained_api_unavailable_does_not_break_baseline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = TrainedDesignService(
        _config(tmp_path, checkpoint_exists=False),
        session_factory=lambda **_: pytest.fail("session must not load"),
    )
    monkeypatch.setattr(main, "trained_design_service", service)
    client = TestClient(main.app)

    status = client.get("/api/v1/design/model/status")
    trained = client.post(
        "/api/v1/design/generate-trained",
        json={"prompt": "Poster spa", "width_mm": 210, "height_mm": 297},
    )
    baseline = client.post(
        "/api/v1/design/generate",
        json={"prompt": "Poster spa", "width_mm": 210, "height_mm": 297},
    )

    assert status.status_code == 200
    assert status.json()["loaded"] is False
    assert trained.status_code == 503
    assert trained.json()["code"] == "trained_design_unavailable"
    assert baseline.status_code == 200
    assert baseline.json()["metadata"]["trained_model"] is False
