from __future__ import annotations

import json
from pathlib import Path

from training.evaluation.critics import HeuristicAestheticCritic
from training.evaluation.layout_metrics import evaluate_layout
from training.evaluation.scoring import DesignScorer, ScoreWeights
from training.inference.candidates import CandidateGenerationSettings
from training.inference.qwen3_planner import RawPlannerGeneration
from training.inference.qwen3_planner import parse_design_output
from training.inference.reference_layout import apply_reference_layout_guidance
from training.inference.rag import (
    ReferenceGroundedDesignPipeline,
    ReferenceGroundedGenerator,
)
from training.retrieval import (
    ReferenceMetadataV1,
    ReferenceRecordV1,
    ReferenceRetriever,
    analyze_brief,
    build_reference_context,
    extract_reference_features,
    summarize_reference,
)
from training.tools.build_reference_corpus import _generic_document


class FakeTokenizer:
    def apply_chat_template(self, messages, **kwargs):  # type: ignore[no-untyped-def]
        return "\n".join(item["content"] for item in messages)

    def __call__(self, value, **kwargs):  # type: ignore[no-untyped-def]
        return {"input_ids": value.split()}


class FakePlanner:
    def __init__(self) -> None:
        self.tokenizer = FakeTokenizer()
        self.prompts: list[str] = []

    def generate_raw(self, **kwargs):  # type: ignore[no-untyped-def]
        self.prompts.append(kwargs["prompt"])
        seed = int(kwargs["seed"])
        offset = seed % 3
        payload = {
            "canvas": {"width": 210, "height": 297, "unit": "mm"},
            "category": "menu",
            "elements": [
                {
                    "type": "text",
                    "name": "Headline",
                    "role": "headline",
                    "text": "MENU NHÀ",
                    "position": {"x": 15, "y": 15},
                    "size": {"width": 180, "height": 30},
                    "font_size": 28,
                },
                {
                    "type": "text",
                    "name": "Menu item",
                    "role": "menu_item",
                    "text": "Món chính với mô tả rất dài cần tự động xuống dòng",
                    "position": {"x": 15, "y": 70 + offset * 8},
                    "size": {"width": 130, "height": 14},
                    "font_size": 22,
                },
                {
                    "type": "text",
                    "name": "Price",
                    "role": "price",
                    "text": "49K",
                    "position": {"x": 160, "y": 70 + offset * 8},
                    "size": {"width": 35, "height": 14},
                    "font_size": 20,
                },
            ],
        }
        return RawPlannerGeneration(
            raw_output=json.dumps(payload, ensure_ascii=False),
            duration_seconds=0.01,
            seed=seed,
            generation_config={"max_new_tokens": kwargs["max_new_tokens"]},
            peak_vram_gib=0.2,
        )


class IdentityAwareFakePlanner(FakePlanner):
    def __init__(self) -> None:
        super().__init__()
        self.identity_request: dict[str, object] | None = None

    def generate_raw_with_identity(self, **kwargs):  # type: ignore[no-untyped-def]
        self.identity_request = dict(kwargs)
        live_kwargs = {
            key: value
            for key, value in kwargs.items()
            if key
            not in {
                "original_prompt",
                "grounded_prompt",
                "reference_context_hash",
                "reference_ids",
            }
        }
        return super().generate_raw(prompt=kwargs["grounded_prompt"], **live_kwargs)


def _record(category: str, variant: str) -> ReferenceRecordV1:
    document = _generic_document(category, variant, ["cream", "gold"])
    features = extract_reference_features(document)
    reference_id = f"fixture:{category}:{variant}"
    metadata = ReferenceMetadataV1(
        reference_id=reference_id,
        category=category,
        format=str(document.metadata["format"]),
        aspect_ratio=float(features.aspect_ratio),
        style_tags=["minimal", variant],
        color_tags=["cream", "gold"],
        text_density=features.text_density,
        element_count=features.element_count,
        layout_features={"composition": features.composition},
        design_document_path=f"documents/{reference_id}.json",
        preview_path=f"previews/{reference_id}.png",
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


class MemoryProvider:
    provider_name = "memory"

    def __init__(self, records: list[ReferenceRecordV1]) -> None:
        self.records = records

    def load_references(self) -> list[ReferenceRecordV1]:
        return list(self.records)


def _scorer() -> DesignScorer:
    return DesignScorer(
        weights=ScoreWeights(
            technical=0.25,
            composition=0.15,
            visual_hierarchy=0.15,
            typography=0.10,
            spacing=0.10,
            color_harmony=0.08,
            balance=0.05,
            readability=0.10,
            prompt_match=0.02,
        ),
        aesthetic_critic=HeuristicAestheticCritic(),
    )


def test_grounded_prompt_is_compact_and_forbids_copying() -> None:
    provider = MemoryProvider([_record("menu", variant) for variant in ("centered", "split")])
    brief = analyze_brief("Food menu 6 items", width=210, height=297)
    retrieval = ReferenceRetriever(provider).retrieve_references(brief, top_k=2)
    context = build_reference_context(retrieval, max_tokens=600)
    planner = FakePlanner()
    generator = ReferenceGroundedGenerator(
        base_generator=planner,
        brief=brief,
        retrieval=retrieval,
        context=context,
    )

    generation = generator.generate_raw(
        prompt=brief.prompt,
        width_mm=210,
        height_mm=297,
        seed=42,
        max_new_tokens=512,
        do_sample=True,
        temperature=0.7,
        top_p=0.8,
        top_k=20,
        repetition_penalty=1.05,
    )

    assert "Do not copy any reference text" in planner.prompts[0]
    assert "exact coordinates" in planner.prompts[0]
    assert generation.generation_config["reference_mode"] == "rag"
    assert generation.generation_config["rag_prompt_tokens"] > generation.generation_config["baseline_prompt_tokens"]
    assert generation.generation_config["reference_prompt_token_delta"] < 1000


def test_grounded_generator_passes_complete_identity_context_when_supported() -> None:
    provider = MemoryProvider([_record("menu", "centered")])
    brief = analyze_brief("Food menu 6 items", width=210, height=297)
    retrieval = ReferenceRetriever(provider).retrieve_references(brief, top_k=1)
    context = build_reference_context(retrieval, max_tokens=350)
    planner = IdentityAwareFakePlanner()
    generator = ReferenceGroundedGenerator(
        base_generator=planner,
        brief=brief,
        retrieval=retrieval,
        context=context,
    )

    generator.generate_raw(
        prompt=brief.prompt,
        width_mm=210,
        height_mm=297,
        seed=42,
        max_new_tokens=512,
        do_sample=True,
        temperature=0.7,
        top_p=0.8,
        top_k=20,
        repetition_penalty=1.05,
    )

    assert planner.identity_request is not None
    assert planner.identity_request["original_prompt"] == brief.prompt
    assert "REFERENCE-GROUNDED MODE" in str(
        planner.identity_request["grounded_prompt"]
    )
    assert planner.identity_request["reference_context_hash"] == generator.context_hash
    assert planner.identity_request["reference_ids"] == generator.reference_ids


def test_rag_pipeline_writes_complete_artifacts_and_fits_text(tmp_path: Path) -> None:
    records = [_record("menu", variant) for variant in ("centered", "split", "grid", "hero_left", "hero_right")]
    run_dir = tmp_path / "rag-run"
    result = ReferenceGroundedDesignPipeline(
        base_generator=FakePlanner(),
        provider=MemoryProvider(records),
        scorer=_scorer(),
        model_provenance={
            "model_id": "Qwen/Qwen3-1.7B",
            "model_revision": "fixture",
            "adapter_checkpoint": "fixture/checkpoint-5",
            "trained_model": True,
        },
        top_k=3,
        context_token_budget=700,
    ).run(
        prompt="Food menu 6 items with prices",
        width_mm=210,
        height_mm=297,
        settings=CandidateGenerationSettings(num_candidates=4, base_seed=70),
        run_dir=run_dir,
    )

    assert result.selection.ranking.winner is not None
    assert {"request.json", "brief.json", "retrieval.json", "reference_context.json", "ranking.json", "performance.json"} <= {path.name for path in run_dir.iterdir()}
    assert len(list((run_dir / "references").glob("ref_*.json"))) == 3
    request = json.loads((run_dir / "request.json").read_text(encoding="utf-8"))
    assert request["reference_mode"] == "rag"
    assert request["commercial_allowed"] is False
    for candidate_dir in (run_dir / "candidates").iterdir():
        assert (candidate_dir / "postprocess.json").is_file()
        postprocess = json.loads(
            (candidate_dir / "postprocess.json").read_text(encoding="utf-8")
        )
        assert postprocess["engine"] == "reference_grounded_postprocessor_v1"
        assert postprocess["reference_layout"]["source_coordinates_copied"] is False
        metrics = json.loads((candidate_dir / "metrics.json").read_text(encoding="utf-8"))
        assert metrics["text_fit_rate"] == 1
        assert metrics["outside_canvas_rate"] == 0
        assert metrics["overlap_ratio"] <= 0.02
        design = json.loads((candidate_dir / "design.json").read_text(encoding="utf-8"))
        assert design["metadata"]["trained_model"] is True
        assert design["source"]["commercial_allowed"] is False


def test_rag_pipeline_visual_mode_is_explicit_and_business_safe(tmp_path: Path) -> None:
    run_dir = tmp_path / "rag-visual-run"
    result = ReferenceGroundedDesignPipeline(
        base_generator=FakePlanner(),
        provider=MemoryProvider([_record("menu", "centered")]),
        scorer=_scorer(),
        model_provenance={
            "model_id": "Qwen/Qwen3-1.7B",
            "model_revision": "fixture",
            "adapter_checkpoint": "fixture/checkpoint-5",
            "trained_model": True,
        },
        top_k=1,
        context_token_budget=350,
        visual_composition=True,
        benchmark_mode=True,
    ).run(
        prompt="Food menu 6 items with prices",
        width_mm=210,
        height_mm=297,
        settings=CandidateGenerationSettings(num_candidates=1, base_seed=91),
        run_dir=run_dir,
    )

    winner = result.selection.ranking.winner
    assert winner == "candidate_01"
    candidate = run_dir / "candidates" / winner
    postprocess = json.loads((candidate / "postprocess.json").read_text(encoding="utf-8"))
    design = json.loads((candidate / "design.json").read_text(encoding="utf-8"))
    placeholders = [
        element
        for element in design["elements"]
        if element["metadata"].get("placeholder_only")
    ]

    assert postprocess["engine"] == "reference_grounded_postprocessor_v0.3.1"
    assert postprocess["visual_composition"]["engine"] == "visual_composition_v0.3.1"
    assert postprocess["visual_metrics"]["asset_intent_preservation"] == 1
    assert len(placeholders) == 12
    assert all(
        item["metadata"]["content_provenance"] == "benchmark_placeholder"
        for item in placeholders
    )
    assert not any(
        (item.get("text") or {}).get("content") in {"39K", "44K", "49K"}
        for item in design["elements"]
    )


def test_reference_layout_recovers_brief_copy_and_drops_empty_placeholders() -> None:
    raw = json.dumps(
        {
            "elements": {
                "headline": {"STRING": "NEW LOOK SALON", "role": "headline"},
                "services": {"role": "body"},
                "empty_cta": {"role": "cta"},
                "hero": {"role": "hero"},
            }
        }
    )
    document, _ = parse_design_output(raw, canvas_width=108, canvas_height=135)
    brief = analyze_brief(
        "Poster salon, headline NEW LOOK SALON, liệt kê cắt uốn nhuộm và số điện thoại",
        width=108,
        height=135,
    )
    retrieval = ReferenceRetriever(MemoryProvider([_record("salon", "centered")])).retrieve_references(
        brief, top_k=1
    )
    context = build_reference_context(retrieval, max_tokens=350)

    grounded, report = apply_reference_layout_guidance(
        document, brief=brief, context=context
    )
    metrics = evaluate_layout(grounded)

    assert report["brief_text_recovery_count"] == 1
    assert report["unresolved_placeholder_drop_count"] == 1
    assert report["preserved_visual_asset_placeholder_count"] == 1
    assert any(
        element.metadata.get("asset_intent", {}).get("role") == "hero"
        for element in grounded.elements
    )
    assert [element.text.content for element in grounded.elements if element.text] == [
        "NEW LOOK SALON",
        "cắt uốn nhuộm và số điện thoại",
    ]
    assert metrics["overlap_ratio"] == 0


def test_reference_layout_keeps_ten_dense_menu_rows_inside_canvas() -> None:
    raw = FakePlanner().generate_raw(
        prompt="Food menu 10 items with prices",
        width_mm=210,
        height_mm=297,
        seed=42,
        max_new_tokens=512,
    ).raw_output
    document, _ = parse_design_output(raw, canvas_width=210, canvas_height=297)
    brief = analyze_brief("Food menu 10 items with prices", width=210, height=297)
    retrieval = ReferenceRetriever(
        MemoryProvider([_record("menu", "centered")])
    ).retrieve_references(brief, top_k=1)
    context = build_reference_context(retrieval, max_tokens=350)

    grounded, report = apply_reference_layout_guidance(
        document, brief=brief, context=context
    )
    metrics = evaluate_layout(grounded)

    assert report["synthetic_menu_element_count"] == 18
    assert metrics["outside_canvas_rate"] == 0
    assert len(
        [element for element in grounded.elements if element.metadata.get("role") == "menu_item"]
    ) == 10
    assert len(
        [element for element in grounded.elements if element.metadata.get("role") == "price"]
    ) == 10
    generated = [
        element
        for element in grounded.elements
        if element.metadata.get("synthetic_brief_completion")
    ]
    assert generated
    assert all(element.metadata["placeholder_only"] is True for element in generated)
    assert all(element.metadata["requires_user_data"] is True for element in generated)
    assert all(
        element.metadata["content_provenance"] == "system_placeholder"
        for element in generated
    )
    assert not any(
        element.text and element.text.content in {"39K", "44K", "49K"}
        for element in generated
    )
