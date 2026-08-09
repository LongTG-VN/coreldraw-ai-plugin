from __future__ import annotations

import json
from pathlib import Path

import pytest

from training.evaluation.critics import HeuristicAestheticCritic, TechnicalCritic
from training.evaluation.diversity import candidate_diversity, layout_distance
from training.evaluation.scoring import (
    AllCandidatesInvalidError,
    DesignScorer,
    ScoreWeights,
    rank_candidate_scores,
)
from training.inference.baseline import generate_baseline_design
from training.inference.candidates import BestOfNSelector, CandidateGenerationSettings
from training.inference.preview import render_preview
from training.inference.qwen3_planner import (
    extract_planner_payload,
    ModelOutputError,
    RawPlannerGeneration,
    parse_design_output,
)
from training.preference.builder import build_preference_record, export_preference
from training.schemas.design import DesignDocument
from training.tools.benchmark_best_of_n import ReusingGenerator


WEIGHTS = ScoreWeights(
    technical=0.25,
    composition=0.15,
    visual_hierarchy=0.15,
    typography=0.10,
    spacing=0.10,
    color_harmony=0.08,
    balance=0.05,
    readability=0.10,
    prompt_match=0.02,
)


class FakeGenerator:
    def __init__(
        self,
        *,
        invalid_seeds: set[int] | None = None,
        error_seeds: set[int] | None = None,
    ) -> None:
        self.invalid_seeds = invalid_seeds or set()
        self.error_seeds = error_seeds or set()
        self.calls: list[dict[str, object]] = []

    def generate_raw(self, **kwargs: object) -> RawPlannerGeneration:
        self.calls.append(kwargs)
        seed = int(kwargs["seed"])
        if seed in self.error_seeds:
            raise RuntimeError("fixture generation failure")
        if seed in self.invalid_seeds:
            raw_output = "no JSON in this candidate"
        else:
            offset = seed % 4
            raw_output = json.dumps(
                {
                    "canvas": {"width": 1000, "height": 500, "unit": "px"},
                    "category": "poster",
                    "elements": [
                        {
                            "type": "text",
                            "text": "SPA CAO CAP",
                            "position": {"x": 100 + offset * 45, "y": 55},
                            "size": 48 + offset * 4,
                            "color": "gold",
                        },
                        {
                            "type": "text",
                            "text": "Thu gian va toa sang",
                            "position": {"x": 140, "y": 350 - offset * 25},
                            "size": 22,
                            "color": "black",
                        },
                    ],
                }
            )
        return RawPlannerGeneration(
            raw_output=raw_output,
            duration_seconds=0.01,
            seed=seed,
            generation_config={"do_sample": bool(kwargs["do_sample"])},
            peak_vram_gib=0.25,
        )


def _scorer() -> DesignScorer:
    return DesignScorer(
        weights=WEIGHTS,
        aesthetic_critic=HeuristicAestheticCritic(),
    )


def _selector(generator: FakeGenerator) -> BestOfNSelector:
    return BestOfNSelector(
        generator=generator,
        scorer=_scorer(),
        model_provenance={
            "model_id": "Qwen/Qwen3-1.7B",
            "model_revision": "fixture-revision",
            "adapter_checkpoint": "fixture/checkpoint-5",
            "trained_model": True,
        },
    )


def test_best_of_n_writes_complete_artifacts_and_deterministic_seeds(
    tmp_path: Path,
) -> None:
    generator = FakeGenerator()
    run_dir = tmp_path / "run"
    result = _selector(generator).run(
        prompt="Poster spa cao cap",
        width_mm=100,
        height_mm=50,
        settings=CandidateGenerationSettings(num_candidates=4, base_seed=91),
        run_dir=run_dir,
    )

    assert [call["seed"] for call in generator.calls] == [91, 92, 93, 94]
    assert result.ranking.winner is not None
    assert result.contact_sheet.is_file()
    assert result.comparison_report.is_file()
    assert (run_dir / "final" / "design.json").is_file()
    assert (run_dir / "final" / "preview.png").is_file()
    assert (run_dir / "final" / "corel_operations.json").is_file()
    for index in range(1, 5):
        directory = run_dir / "candidates" / f"candidate_{index:02d}"
        assert {
            "raw_output.txt",
            "generation.json",
            "planner.json",
            "design.json",
            "corel_operations.json",
            "preview.png",
            "validation.json",
            "metrics.json",
            "score.json",
        } <= {path.name for path in directory.iterdir()}
    request = json.loads((run_dir / "request.json").read_text(encoding="utf-8"))
    assert request["license_class"] == "research_only"
    assert request["commercial_allowed"] is False


def test_same_seed_reproduces_raw_outputs_and_ranking(tmp_path: Path) -> None:
    settings = CandidateGenerationSettings(num_candidates=3, base_seed=101)
    results = [
        _selector(FakeGenerator()).run(
            prompt="Poster spa",
            width_mm=100,
            height_mm=50,
            settings=settings,
            run_dir=tmp_path / f"repeat-{index}",
        )
        for index in range(2)
    ]

    assert [
        record.raw_output for record in results[0].candidates.values()
    ] == [record.raw_output for record in results[1].candidates.values()]
    assert results[0].ranking == results[1].ranking
    assert results[0].diversity == results[1].diversity


def test_invalid_candidate_is_hard_failed_without_blocking_valid_winner(
    tmp_path: Path,
) -> None:
    result = _selector(FakeGenerator(invalid_seeds={12})).run(
        prompt="Poster spa",
        width_mm=100,
        height_mm=50,
        settings=CandidateGenerationSettings(num_candidates=3, base_seed=11),
        run_dir=tmp_path / "partial",
    )

    invalid = result.candidates["candidate_02"]
    assert invalid.score.eligible is False
    assert invalid.score.technical.hard_failure is True
    assert invalid.score.final_score == 0
    assert result.ranking.winner != "candidate_02"
    assert (invalid.directory / "validation.json").is_file()


def test_generation_exception_is_isolated_to_one_candidate(tmp_path: Path) -> None:
    result = _selector(FakeGenerator(error_seeds={52})).run(
        prompt="Poster spa",
        width_mm=100,
        height_mm=50,
        settings=CandidateGenerationSettings(num_candidates=3, base_seed=51),
        run_dir=tmp_path / "generation-error",
    )

    failed = result.candidates["candidate_02"]
    assert failed.validation["failure_stage"] == "generation"
    assert failed.score.eligible is False
    assert result.ranking.winner != "candidate_02"
    assert failed.generation["generation_error"]["error_type"] == "RuntimeError"


def test_all_invalid_candidates_raise_after_diagnostic_artifacts(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "all-invalid"
    with pytest.raises(AllCandidatesInvalidError) as exc_info:
        _selector(FakeGenerator(invalid_seeds={7, 8})).run(
            prompt="Poster spa",
            width_mm=100,
            height_mm=50,
            settings=CandidateGenerationSettings(num_candidates=2, base_seed=7),
            run_dir=run_dir,
        )

    assert exc_info.value.ranking.all_candidates_invalid is True
    assert (run_dir / "ranking.json").is_file()
    assert (run_dir / "contact_sheet.png").is_file()
    assert not (run_dir / "final").exists()
    diversity = json.loads((run_dir / "ranking.json").read_text(encoding="utf-8"))[
        "diversity"
    ]
    assert diversity["meaningful_diversity"] is False
    assert diversity["warning"]


def test_all_invalid_benchmark_mode_returns_diagnostics(tmp_path: Path) -> None:
    result = _selector(FakeGenerator(invalid_seeds={7, 8})).run(
        prompt="Poster spa",
        width_mm=100,
        height_mm=50,
        settings=CandidateGenerationSettings(num_candidates=2, base_seed=7),
        run_dir=tmp_path / "all-invalid-benchmark",
        raise_on_all_invalid=False,
    )

    assert result.ranking.winner is None
    assert result.ranking.all_candidates_invalid is True
    assert result.contact_sheet.is_file()
    assert not (result.run_dir / "final").exists()


def test_single_candidate_fallback_and_no_overwrite(tmp_path: Path) -> None:
    run_dir = tmp_path / "single"
    result = _selector(FakeGenerator()).run(
        prompt="Poster spa",
        width_mm=100,
        height_mm=50,
        settings=CandidateGenerationSettings(num_candidates=1, base_seed=3),
        run_dir=run_dir,
    )

    assert result.ranking.winner == "candidate_01"
    assert result.diversity["meaningful_diversity"] is False
    assert "Only one valid" in str(result.diversity["warning"])
    with pytest.raises(ValueError, match="at least two"):
        build_preference_record(run_dir)
    with pytest.raises(FileExistsError):
        _selector(FakeGenerator()).run(
            prompt="Poster spa",
            width_mm=100,
            height_mm=50,
            settings=CandidateGenerationSettings(num_candidates=1),
            run_dir=run_dir,
        )


@pytest.mark.parametrize(
    ("prompt", "width_mm", "height_mm", "message"),
    [
        ("", 100, 50, "prompt"),
        ("Poster", 0, 50, "width_mm"),
        ("Poster", 100, float("nan"), "height_mm"),
    ],
)
def test_selector_rejects_invalid_request_before_writing(
    tmp_path: Path,
    prompt: str,
    width_mm: float,
    height_mm: float,
    message: str,
) -> None:
    run_dir = tmp_path / "invalid-request"
    with pytest.raises(ValueError, match=message):
        _selector(FakeGenerator()).run(
            prompt=prompt,
            width_mm=width_mm,
            height_mm=height_mm,
            settings=CandidateGenerationSettings(num_candidates=1),
            run_dir=run_dir,
        )
    assert not run_dir.exists()


def test_ranking_uses_stable_candidate_id_tie_breaker(tmp_path: Path) -> None:
    document = generate_baseline_design("Poster spa", 100, 50)
    preview = render_preview(document, tmp_path / "preview.png")
    score = _scorer().score(
        prompt="Poster spa",
        document=document,
        preview_path=preview,
    )

    ranking = rank_candidate_scores({"candidate_02": score, "candidate_01": score})

    assert [item.candidate_id for item in ranking.candidates] == [
        "candidate_01",
        "candidate_02",
    ]
    assert ranking.winner == "candidate_01"


def test_technical_hard_failure_and_aesthetic_scale(tmp_path: Path) -> None:
    hard_failure = TechnicalCritic().score(None)
    assert hard_failure.hard_failure is True
    assert hard_failure.overall == 0
    assert hard_failure.violations[0].code == "invalid_schema"

    document = generate_baseline_design("Poster spa cao cap", 100, 50)
    preview = render_preview(document, tmp_path / "preview.png")
    score = _scorer().score(
        prompt="Poster spa cao cap",
        document=document,
        preview_path=preview,
    )
    assert score.eligible is True
    assert score.aesthetic is not None
    assert score.aesthetic.model_based is False
    for field in (
        "composition",
        "visual_hierarchy",
        "typography",
        "spacing",
        "color_harmony",
        "balance",
        "readability",
        "style_match",
    ):
        assert 0 <= getattr(score.aesthetic, field) <= 1


def test_technical_overlap_penalty_does_not_saturate_early() -> None:
    low_overlap = generate_baseline_design("Poster", 100, 50)
    medium_payload = low_overlap.model_dump()
    medium_payload["elements"][2]["bbox"] = {
        "x": 10,
        "y": 10,
        "width": 80,
        "height": 12,
    }
    medium_payload["elements"][2]["bbox_norm"] = {
        "x": 0.1,
        "y": 0.2,
        "width": 0.8,
        "height": 0.24,
    }
    medium_overlap = DesignDocument.model_validate(medium_payload)
    severe_payload = medium_overlap.model_dump()
    severe_payload["elements"][2]["bbox"] = {
        "x": 10,
        "y": 6,
        "width": 80,
        "height": 12,
    }
    severe_payload["elements"][2]["bbox_norm"] = {
        "x": 0.1,
        "y": 0.12,
        "width": 0.8,
        "height": 0.24,
    }
    severe_overlap = DesignDocument.model_validate(severe_payload)

    medium_score = TechnicalCritic().score(medium_overlap)
    severe_score = TechnicalCritic().score(severe_overlap)

    assert medium_score.metrics["overlap_ratio"] < severe_score.metrics["overlap_ratio"]
    assert medium_score.overall > severe_score.overall


def test_text_box_overflow_is_measured_and_penalized() -> None:
    fitting = generate_baseline_design("Poster", 100, 50)
    overflow_payload = fitting.model_dump()
    text_element = overflow_payload["elements"][1]
    text_element["bbox"] = {"x": 10, "y": 5, "width": 20, "height": 3}
    text_element["bbox_norm"] = {
        "x": 0.1,
        "y": 0.1,
        "width": 0.2,
        "height": 0.06,
    }
    text_element["text"]["content"] = "A VERY LONG HEADLINE THAT MUST WRAP"
    text_element["text"]["font_size"] = 20
    overflowing = DesignDocument.model_validate(overflow_payload)

    fitting_score = TechnicalCritic().score(fitting)
    overflow_score = TechnicalCritic().score(overflowing)

    assert fitting_score.metrics["text_fit_rate"] > overflow_score.metrics["text_fit_rate"]
    assert overflow_score.metrics["text_overflow_count"] >= 1
    assert any(
        violation.code == "text_box_overflow"
        for violation in overflow_score.violations
    )
    assert fitting_score.overall > overflow_score.overall


def test_truncated_output_recovery_has_distinct_penalty() -> None:
    complete = generate_baseline_design("Poster", 100, 50)
    truncated_payload = complete.model_dump()
    truncated_payload["metadata"]["truncated_json_recovery"] = True
    truncated = DesignDocument.model_validate(truncated_payload)

    complete_score = TechnicalCritic().score(
        complete, validation={"raw_schema_valid": False}
    )
    truncated_score = TechnicalCritic().score(
        truncated, validation={"raw_schema_valid": False}
    )

    assert any(
        violation.code == "truncated_model_output"
        for violation in truncated_score.violations
    )
    assert complete_score.overall > truncated_score.overall


def test_aesthetic_readability_rewards_text_background_contrast(
    tmp_path: Path,
) -> None:
    readable = generate_baseline_design("Poster", 100, 50)
    low_contrast_payload = readable.model_dump()
    for element in low_contrast_payload["elements"]:
        if element["type"] == "text":
            element["visual"]["fill"] = {"model": "hex", "values": ["#FFFFFF"]}
    low_contrast = DesignDocument.model_validate(low_contrast_payload)
    readable_preview = render_preview(readable, tmp_path / "readable.png")
    low_contrast_preview = render_preview(low_contrast, tmp_path / "low-contrast.png")

    readable_score = _scorer().score(
        prompt="Poster",
        document=readable,
        preview_path=readable_preview,
    )
    low_contrast_score = _scorer().score(
        prompt="Poster",
        document=low_contrast,
        preview_path=low_contrast_preview,
    )

    assert readable_score.aesthetic is not None
    assert low_contrast_score.aesthetic is not None
    assert (
        readable_score.aesthetic.readability
        > low_contrast_score.aesthetic.readability
    )
    assert readable_score.final_score > low_contrast_score.final_score


def test_scorer_provenance_comes_from_configured_critic() -> None:
    critic = HeuristicAestheticCritic()
    critic.critic_name = "fixture_critic"
    critic.critic_version = "9.1"
    critic.model_based = True
    provenance = DesignScorer(weights=WEIGHTS, aesthetic_critic=critic).provenance()

    assert provenance == {
        "technical": "deterministic_technical_critic:0.2.3",
        "aesthetic": "fixture_critic:9.1",
        "vision_model_used": True,
    }


def test_internal_critic_failure_is_not_mislabeled_as_model_failure(
    tmp_path: Path,
) -> None:
    class ExplodingCritic(HeuristicAestheticCritic):
        def score(self, **kwargs: object):  # type: ignore[no-untyped-def]
            raise RuntimeError("critic infrastructure failure")

    selector = BestOfNSelector(
        generator=FakeGenerator(),
        scorer=DesignScorer(weights=WEIGHTS, aesthetic_critic=ExplodingCritic()),
        model_provenance={"trained_model": True},
    )
    with pytest.raises(RuntimeError, match="critic infrastructure failure"):
        selector.run(
            prompt="Poster spa",
            width_mm=100,
            height_mm=50,
            settings=CandidateGenerationSettings(num_candidates=2),
            run_dir=tmp_path / "critic-error",
        )


def test_diversity_detects_geometry_change() -> None:
    first = generate_baseline_design("Poster", 100, 50)
    payload = first.model_dump()
    payload["elements"][1]["bbox"] = {"x": 50, "y": 5, "width": 40, "height": 12}
    payload["elements"][1]["bbox_norm"] = {
        "x": 0.5,
        "y": 0.1,
        "width": 0.4,
        "height": 0.24,
    }
    second = DesignDocument.model_validate(payload)

    assert layout_distance(first, first) == 0
    assert layout_distance(first, second) > 0
    report = candidate_diversity({"a": first, "b": second})
    assert report["average_layout_distance"] > 0


def test_preference_export_distinguishes_auto_and_human(tmp_path: Path) -> None:
    run_dir = tmp_path / "preferences"
    result = _selector(FakeGenerator()).run(
        prompt="Poster spa",
        width_mm=100,
        height_mm=50,
        settings=CandidateGenerationSettings(num_candidates=3, base_seed=31),
        run_dir=run_dir,
    )
    auto = build_preference_record(run_dir)
    human_choice = next(
        candidate_id
        for candidate_id in result.candidates
        if candidate_id != result.ranking.winner
    )
    human_rejected = next(
        candidate_id
        for candidate_id in result.candidates
        if candidate_id not in {result.ranking.winner, human_choice}
    )
    human_path = export_preference(
        run_dir,
        run_dir / "preference.human.json",
        preference_type="human_preference",
        chosen_candidate_id=human_choice,
        rejected_candidate_id=human_rejected,
    )
    human = json.loads(human_path.read_text(encoding="utf-8"))

    assert auto["metadata"]["preference_type"] == "auto_preference"
    assert auto["metadata"]["human_approved"] is False
    assert auto["metadata"]["commercial_allowed"] is False
    assert auto["chosen"]["candidate_id"] == result.ranking.winner
    assert human["metadata"]["preference_type"] == "human_preference"
    assert human["metadata"]["human_approved"] is True
    assert human["chosen"]["candidate_id"] == human_choice
    assert human["rejected"]["candidate_id"] == human_rejected


def test_human_preference_requires_explicit_distinct_pair(tmp_path: Path) -> None:
    run_dir = tmp_path / "human-pair"
    _selector(FakeGenerator()).run(
        prompt="Poster spa",
        width_mm=100,
        height_mm=50,
        settings=CandidateGenerationSettings(num_candidates=2),
        run_dir=run_dir,
    )

    with pytest.raises(ValueError, match="rejected_candidate_id"):
        build_preference_record(
            run_dir,
            preference_type="human_preference",
            chosen_candidate_id="candidate_01",
        )
    with pytest.raises(ValueError, match="must differ"):
        build_preference_record(
            run_dir,
            preference_type="human_preference",
            chosen_candidate_id="candidate_01",
            rejected_candidate_id="candidate_01",
        )


def test_human_preference_cannot_choose_invalid_candidate(tmp_path: Path) -> None:
    run_dir = tmp_path / "human-invalid"
    _selector(FakeGenerator(invalid_seeds={42})).run(
        prompt="Poster spa",
        width_mm=100,
        height_mm=50,
        settings=CandidateGenerationSettings(num_candidates=2, base_seed=42),
        run_dir=run_dir,
    )

    with pytest.raises(ValueError, match="cannot choose an invalid"):
        build_preference_record(
            run_dir,
            preference_type="human_preference",
            chosen_candidate_id="candidate_01",
            rejected_candidate_id="candidate_02",
        )


@pytest.mark.parametrize(
    "wrapper",
    [None, "design", "design_document", "layout"],
)
def test_parser_recovers_observed_qwen_canvas_size_wrappers(
    wrapper: str | None,
) -> None:
    body = {
        "schema_version": 0.1,
        "canvas_size": {"width": 400, "height": 120},
        "elements": [
            {
                "type": "text",
                "text": "SPA CAO CAP",
                "position": {"x": 0, "y": 0},
                "font_size": 24,
                "font_family": "Arial",
            },
            {
                "type": "image",
                "image_url": "https://example.com/remote.jpg",
                "position": {"x": 100, "y": 90},
                "size": {"width": 100, "height": 100},
            },
        ],
    }
    payload = {wrapper: body} if wrapper else body

    document, validation = parse_design_output(json.dumps(payload))

    assert validation["strict_schema_valid"] is True
    assert validation["raw_schema_valid"] is False
    assert document.canvas.width == 400
    assert document.elements[1].text is not None
    assert document.elements[1].text.font_size == 24
    assert document.elements[1].bbox.x == 0
    assert document.elements[1].bbox.y == 0
    assert document.elements[2].bbox.y + document.elements[2].bbox.height <= 120
    assert document.elements[2].metadata["asset_intent"]["remote_source_rejected"]


def test_parser_recovers_canvas_size_array() -> None:
    raw_output = json.dumps(
        {
            "layout": {
                "canvas_size": [108, 135],
                "elements": [
                    {
                        "type": "text",
                        "text": "LUNA NAIL",
                        "position": {"x": 5, "y": 10},
                        "font_size": 18,
                    }
                ],
            }
        }
    )

    document, validation = parse_design_output(raw_output)

    assert validation["strict_schema_valid"] is True
    assert document.canvas.width == 108
    assert document.canvas.height == 135
    assert document.metadata["schema_wrapper"] == "layout"


def test_parser_recovers_named_element_map_and_array_geometry() -> None:
    raw_output = json.dumps(
        {
            "design": {
                "canvas_size": [108, 135],
                "elements": {
                    "header": {
                        "position": [10, 20],
                        "size": [90, 30],
                        "text": "PURE GLOW",
                        "font_size": 24,
                    },
                    "hero": {
                        "position": [10, 60],
                        "size": [50, 60],
                    },
                },
            }
        }
    )

    document, validation = parse_design_output(raw_output)

    assert validation["strict_schema_valid"] is True
    assert len(document.elements) == 3
    assert document.elements[1].type == "text"
    assert document.elements[1].bbox.x == 10
    assert document.elements[2].type == "rectangle"


def test_parser_explicitly_recovers_complete_truncated_element_prefix() -> None:
    raw_output = """{
      "canvas_size": {"width": 210, "height": 297},
      "elements": [
        {"type": "text", "text": "QUE NHA", "position": {"x": 10, "y": 10}, "font_size": 24},
        {"type": "text", "text": "BROKEN
    """

    document, validation = parse_design_output(raw_output)

    assert validation == {
        "strict_schema_valid": True,
        "raw_schema_valid": False,
        "recovery_steps": ["recovered_truncated_element_prefix"],
    }
    assert document.metadata["truncated_json_recovery"] is True
    assert document.metadata["complete_prefix_element_count"] == 1
    assert document.elements[1].text is not None
    assert document.elements[1].text.content == "QUE NHA"
    planner = extract_planner_payload(raw_output)
    assert planner["recovery"] == "truncated_element_prefix"
    assert planner["complete_prefix_element_count"] == 1
    assert planner["normalized_design"]["schema_version"] == "0.1"


@pytest.mark.parametrize("raw_output", ["no json", "{not valid json"])
def test_parser_error_always_retains_raw_output(raw_output: str) -> None:
    with pytest.raises(ModelOutputError) as exc_info:
        parse_design_output(raw_output)

    assert exc_info.value.raw_output == raw_output


def test_benchmark_dimensions_are_real_millimetres() -> None:
    config_path = (
        Path(__file__).resolve().parents[1]
        / "training"
        / "config"
        / "benchmarks"
        / "design_v0_2.json"
    )
    config = json.loads(config_path.read_text(encoding="utf-8"))

    assert len(config["prompts"]) >= 10
    assert all(0 < row["width_mm"] <= 500 for row in config["prompts"])
    assert all(0 < row["height_mm"] <= 297 for row in config["prompts"])
    a4 = next(row for row in config["prompts"] if row["id"] == "restaurant_menu")
    assert (a4["width_mm"], a4["height_mm"]) == (210, 297)
    assert a4["max_new_tokens"] == 768
    dense = next(row for row in config["prompts"] if row["id"] == "dense_food_menu")
    assert dense["max_new_tokens"] == 1024


def test_benchmark_reuses_only_exact_model_and_generation_request(
    tmp_path: Path,
) -> None:
    model = {
        "model_id": "Qwen/Qwen3-1.7B",
        "model_revision": "fixture-revision",
        "adapter_checkpoint": "fixture-checkpoint",
    }
    run_dir = tmp_path / "cache" / "runs" / "spa"
    candidate_dir = run_dir / "candidates" / "candidate_01"
    candidate_dir.mkdir(parents=True)
    request = {
        "prompt": "Poster spa",
        "width_mm": 100,
        "height_mm": 50,
        "model": model,
    }
    generation_config = {
        "max_new_tokens": 512,
        "do_sample": True,
        "temperature": 0.7,
        "top_p": 0.8,
        "top_k": 20,
        "repetition_penalty": 1.05,
    }
    (run_dir / "request.json").write_text(json.dumps(request), encoding="utf-8")
    (candidate_dir / "raw_output.txt").write_text("cached", encoding="utf-8")
    (candidate_dir / "generation.json").write_text(
        json.dumps(
            {
                "seed": 42,
                "duration_seconds": 10.0,
                "peak_vram_gib": 1.2,
                "config": generation_config,
            }
        ),
        encoding="utf-8",
    )

    live = FakeGenerator()
    generator = ReusingGenerator(
        live=live,  # type: ignore[arg-type]
        cache_root=tmp_path / "cache",
        expected_model=model,
    )
    kwargs = {
        "prompt": "Poster spa",
        "width_mm": 100,
        "height_mm": 50,
        "seed": 42,
        **generation_config,
    }
    cached = generator.generate_raw(**kwargs)
    live_result = generator.generate_raw(**{**kwargs, "seed": 43})

    assert cached.raw_output == "cached"
    assert cached.generation_config["reused_raw_output"] is True
    assert generator.reuse_hits == 1
    assert live_result.raw_output != "cached"
    assert len(live.calls) == 1
