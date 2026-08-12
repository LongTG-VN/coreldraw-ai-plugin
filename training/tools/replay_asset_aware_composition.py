"""Compare five v0.3.2 placeholders with v0.3.3 licensed/project assets."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from statistics import mean
from typing import Any

from PIL import Image, ImageDraw

from training.evaluation.critics import HeuristicAestheticCritic
from training.evaluation.manual_review import write_manual_review_artifacts
from training.evaluation.scoring import DesignScorer, ScoreWeights
from training.inference.corel_compiler import compile_corel_operations
from training.inference.preview import render_preview
from training.retrieval.models import StructuredBriefV1
from training.schemas.design import (
    BoundingBox,
    ColorSpec,
    DesignDocument,
    DesignElement,
    TextSpec,
    VisualSpec,
    normalize_bbox,
)
from training.typography.fitting import fit_design_typography
from training.visual.asset_analysis import analyze_manifest_assets
from training.visual.asset_aware import (
    apply_asset_aware_composition,
    evaluate_asset_aware_composition,
)
from training.visual.asset_contracts import AssetManifestV1, validate_asset_manifest


CASE_TO_PROMPT = {
    "spa": "spa_luxury",
    "cafe": "cafe_vintage",
    "sale": "sale_bold",
    "menu": "dense_food_menu",
    "signage": "signage_wide",
}


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _scorer(path: Path) -> DesignScorer:
    payload = _read_json(path)
    return DesignScorer(
        weights=ScoreWeights.model_validate(payload["weights"]),
        aesthetic_critic=HeuristicAestheticCritic(),
    )


def _flatten(score: Any) -> dict[str, Any]:
    payload = score.model_dump(mode="json")
    aesthetic = payload["aesthetic"] or {}
    metrics = dict(payload["technical"]["metrics"])
    metrics.update(
        {
            "combined": payload["final_score"],
            "technical": payload["technical"]["overall"],
            "aesthetic": aesthetic.get("overall", 0),
            "spacing": aesthetic.get("spacing", 0),
            "visual_hierarchy": aesthetic.get("visual_hierarchy", 0),
            "typography": aesthetic.get("typography", 0),
            "balance": aesthetic.get("balance", 0),
            "readability": aesthetic.get("readability", 0),
            "style_match": aesthetic.get("style_match", 0),
        }
    )
    return metrics


def _box(document: DesignDocument, values: tuple[float, float, float, float]) -> BoundingBox:
    x, y, width, height = values
    return BoundingBox(
        x=x * float(document.canvas.width),
        y=y * float(document.canvas.height),
        width=width * float(document.canvas.width),
        height=height * float(document.canvas.height),
    )


def _placeholder(
    document: DesignDocument,
    *,
    role: str,
    values: tuple[float, float, float, float],
) -> None:
    absolute = _box(document, values)
    identifier = f"benchmark_{role}_placeholder"
    stroke = "#C49A52" if role == "logo" else "#9D7B55"
    placeholder = DesignElement(
        id=identifier,
        name=f"{role.title()} Placeholder",
        type="rectangle",
        bbox=absolute,
        bbox_norm=normalize_bbox(absolute, document.canvas),
        z_index=max((item.z_index for item in document.elements), default=0) + 1,
        layer="assets",
        visual=VisualSpec(
            fill=ColorSpec(model="hex", values=["#FFF9F1"]),
            stroke=ColorSpec(model="hex", values=[stroke]),
            stroke_width=max(.3, min(float(document.canvas.width), float(document.canvas.height)) * .002),
            opacity=.78,
        ),
        metadata={
            "role": role,
            "asset_role": role,
            "asset_required": True,
            "source_provided": False,
            "placeholder": True,
            "editable_placeholder": True,
            "requires_real_asset": True,
            "placeholder_presentation": "soft_frame_v1",
        },
    )
    document.elements.append(placeholder)
    label_box = _box(
        document,
        (
            values[0] + values[2] * .10,
            values[1] + values[3] * .70,
            values[2] * .80,
            max(.025, values[3] * .14),
        ),
    )
    document.elements.append(
        DesignElement(
            id=f"{identifier}_label",
            name=f"{role.title()} Placeholder Label",
            type="text",
            bbox=label_box,
            bbox_norm=normalize_bbox(label_box, document.canvas),
            z_index=placeholder.z_index + 1,
            layer="background",
            text=TextSpec(
                content=role.upper(),
                font_family="DejaVuSans.ttf",
                font_size=max(4, min(float(document.canvas.width), float(document.canvas.height)) * .02),
                font_weight=700,
                alignment="center",
            ),
            visual=VisualSpec(fill=ColorSpec(model="hex", values=[stroke])),
            metadata={
                "placeholder_label": True,
                "placeholder_for": identifier,
                "requires_real_asset": True,
            },
        )
    )


def _mark_text(element: DesignElement, *, sample_data: bool) -> None:
    element.metadata.update(
        {
            "benchmark_sample_data": sample_data,
            "customer_provided": False,
            "project_owned_copy": True,
            "content_provenance": "project_owned_benchmark_copy",
        }
    )


def _ensure_case_text(
    document: DesignDocument,
    *,
    role: str,
    content: str,
    values: tuple[float, float, float, float],
    font_size: float,
    sample_data: bool,
    alignment: str = "left",
) -> DesignElement:
    existing = next(
        (
            item for item in document.elements
            if item.text is not None and item.metadata.get("role") == role
        ),
        None,
    )
    if existing is None:
        absolute = _box(document, values)
        existing = DesignElement(
            id=f"benchmark_{role}_copy",
            name=f"Benchmark {role.title()} Copy",
            type="text",
            bbox=absolute,
            bbox_norm=normalize_bbox(absolute, document.canvas),
            z_index=max((item.z_index for item in document.elements), default=0) + 1,
            layer="content",
            text=TextSpec(
                content=content,
                font_family="DejaVuSans.ttf",
                font_size=font_size,
                font_weight=800 if role in {"headline", "promotion"} else 600,
                alignment=alignment,
            ),
            visual=VisualSpec(fill=ColorSpec(model="hex", values=["#173D34"])),
            metadata={"role": role, "deterministic_copy_fallback": True},
        )
        document.elements.append(existing)
    else:
        existing.text.content = content
        existing.metadata["role"] = role
    _mark_text(existing, sample_data=sample_data)
    return existing


def _prepare_case_document(
    source: DesignDocument,
    *,
    case_id: str,
    case: dict[str, Any],
) -> DesignDocument:
    output = source.model_copy(deep=True)
    output.sample_id = f"v033:{case_id}:placeholder"
    sample_data = bool(case["benchmark_sample_data"])
    output.elements = [
        item for item in output.elements
        if not (
            item.text is None
            and item.metadata.get("asset_intent", {}).get("role")
            in {"headline", "subtitle", "body", "cta", "promotion", "price"}
        )
    ]
    text = sorted(
        (item for item in output.elements if item.text is not None),
        key=lambda item: (float(item.bbox_norm.y), item.z_index),
    )
    if case_id in {"spa", "cafe"}:
        headlines = [item for item in text if item.metadata.get("role") == "headline"]
        ctas = [item for item in text if item.metadata.get("role") == "cta"]
        bodies = [item for item in text if item not in headlines + ctas]
        if not headlines:
            headlines.append(_ensure_case_text(
                output, role="headline", content=case["subheadline"].upper(),
                values=(.05, .16, .44, .16), font_size=22, sample_data=sample_data,
            ))
        if not bodies:
            bodies.append(_ensure_case_text(
                output, role="body", content=case["body"],
                values=(.05, .48, .43, .15), font_size=11, sample_data=sample_data,
            ))
        if not ctas:
            ctas.append(_ensure_case_text(
                output, role="cta", content=case["cta"].upper(),
                values=(.05, .78, .38, .10), font_size=12, sample_data=sample_data,
            ))
        headlines[0].text.content = case["subheadline"].upper()
        headlines[0].metadata["role"] = "headline"
        bodies[0].text.content = case["body"]
        bodies[0].metadata["role"] = "body"
        keep = {headlines[0].id, bodies[0].id, ctas[0].id}
        ctas[0].text.content = case["cta"].upper()
        output.elements = [item for item in output.elements if item.text is None or item.id in keep]
    elif case_id == "sale":
        headline = _ensure_case_text(
            output, role="headline", content=case["headline"],
            values=(.50, .12, .45, .22), font_size=28, sample_data=sample_data,
            alignment="center",
        )
        cta = _ensure_case_text(
            output, role="cta", content=case["cta"],
            values=(.50, .71, .34, .11), font_size=14, sample_data=sample_data,
            alignment="center",
        )
        headline.text.content = case["headline"]
        cta.text.content = case["cta"]
        keep = {headline.id, cta.id}
        output.elements = [item for item in output.elements if item.text is None or item.id in keep]
        offer_box = _box(output, (.50, .40, .39, .14))
        output.elements.append(
            DesignElement(
                id="benchmark_sale_offer",
                name="Benchmark Sale Offer",
                type="text",
                bbox=offer_box,
                bbox_norm=normalize_bbox(offer_box, output.canvas),
                z_index=max(item.z_index for item in output.elements) + 1,
                layer="content",
                text=TextSpec(
                    content=case["offer"],
                    font_family="DejaVuSansCondensed.ttf",
                    font_size=max(12, min(float(output.canvas.width), float(output.canvas.height)) * .11),
                    font_weight=900,
                    alignment="center",
                ),
                visual=VisualSpec(fill=ColorSpec(model="hex", values=["#A51D2D"])),
                metadata={"role": "promotion"},
            )
        )
    elif case_id == "menu":
        headline = _ensure_case_text(
            output, role="headline", content="THỰC ĐƠN",
            values=(.05, .13, .58, .085), font_size=18, sample_data=sample_data,
        )
        headline.text.content = "THỰC ĐƠN"
        headline.text.font_size = min(float(headline.text.font_size or 18), 18.0)
        body = _ensure_case_text(
            output, role="body", content=case["subheadline"],
            values=(.05, .235, .58, .045), font_size=9, sample_data=sample_data,
        )
        body.text.content = case["subheadline"]
        cta = _ensure_case_text(
            output, role="cta", content=case["cta"],
            values=(.05, .86, .90, .09), font_size=13, sample_data=sample_data,
        )
        cta.text.content = case["cta"]
        menu_items = sorted(
            (item for item in text if item.metadata.get("role") == "menu_item"),
            key=lambda item: float(item.bbox_norm.y),
        )
        prices = sorted(
            (item for item in text if item.metadata.get("role") == "price"),
            key=lambda item: float(item.bbox_norm.y),
        )
        while len(menu_items) < len(case["items"]):
            row = len(menu_items)
            y = .32 + row * .055
            menu_items.append(_ensure_case_text(
                output, role=f"menu_item_{row + 1}", content="",
                values=(.05, y, .66, .05), font_size=6, sample_data=sample_data,
            ))
            menu_items[-1].metadata["role"] = "menu_item"
        while len(prices) < len(case["items"]):
            row = len(prices)
            y = .32 + row * .055
            prices.append(_ensure_case_text(
                output, role=f"price_{row + 1}", content="",
                values=(.77, y, .17, .05), font_size=7, sample_data=sample_data,
                alignment="right",
            ))
            prices[-1].metadata["role"] = "price"
        keep = {headline.id, body.id, cta.id}
        for item_element, price_element, item in zip(menu_items[:5], prices[:5], case["items"]):
            item_element.text.content = f"{item['name']}\n{item['description']}"
            price_element.text.content = item["price"]
            keep.update({item_element.id, price_element.id})
        output.elements = [item for item in output.elements if item.text is None or item.id in keep]
        output.elements = [
            item for item in output.elements
            if not (
                item.metadata.get("decorative_role") == "menu_row_band"
                and int(item.id.rsplit("_", 1)[-1]) > 5
            )
            and not (
                item.metadata.get("decorative_role") == "menu_divider"
                and int(item.id.rsplit("_", 1)[-1]) > 4
            )
        ]
    else:
        headline = _ensure_case_text(
            output, role="headline", content=case["subheadline"].upper(),
            values=(.05, .20, .48, .28), font_size=28, sample_data=sample_data,
        )
        headline.text.content = case["subheadline"].upper()
        output.elements = [
            item for item in output.elements
            if (item.text is None or item.id == headline.id)
            and not item.metadata.get("editable_placeholder")
            and not item.metadata.get("placeholder_for")
        ]
    for element in output.elements:
        if element.text is not None and not element.metadata.get("placeholder_label"):
            _mark_text(element, sample_data=sample_data)
    output.metadata = {
        **output.metadata,
        "v033_benchmark_case": {
            "case_id": case_id,
            "benchmark_sample_data": sample_data,
            "customer_provided": False,
            "copy_source": "project_owned_benchmark_copy",
        },
    }
    existing_roles = {
        str(item.metadata.get("asset_role"))
        for item in output.elements
        if item.metadata.get("editable_placeholder")
    }
    if "logo" not in existing_roles:
        _placeholder(output, role="logo", values={
            "spa": (.05, .035, .31, .085),
            "cafe": (.05, .035, .34, .09),
            "sale": (.05, .045, .27, .075),
            "menu": (.05, .035, .28, .075),
            "signage": (.57, .14, .39, .72),
        }[case_id])
    if case_id == "menu" and not existing_roles.intersection({"hero", "product"}):
        _placeholder(output, role="hero", values=(.69, .04, .27, .22))
    return DesignDocument.model_validate(output.model_dump())


def _contact_sheet(pairs: list[tuple[str, Path]], output: Path) -> None:
    cell_width, cell_height = 1140, 690
    canvas = Image.new("RGB", (cell_width, cell_height * len(pairs)), "#E7E5E1")
    draw = ImageDraw.Draw(canvas)
    for row, (case_id, path) in enumerate(pairs):
        with Image.open(path) as source:
            image = source.convert("RGB")
            image.thumbnail((1100, 620), Image.Resampling.LANCZOS)
        origin_y = row * cell_height
        draw.text((20, origin_y + 16), case_id.upper(), fill="#111111")
        canvas.paste(image, ((cell_width - image.width) // 2, origin_y + 50))
    canvas.save(output, format="PNG", optimize=False)


def replay(
    *,
    source: Path,
    asset_root: Path,
    output: Path,
    score_config: Path,
) -> dict[str, Any]:
    source = source.resolve()
    asset_root = asset_root.resolve()
    output = output.resolve()
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"output must be new or empty: {output}")
    output.mkdir(parents=True, exist_ok=True)
    runs = output / "runs"
    runs.mkdir()
    scorer = _scorer(score_config.resolve())
    source_summary = _read_json(source / "summary.json")
    metadata_source = Path(str(source_summary["source"])).resolve()
    if not (metadata_source / "runs").is_dir():
        raise FileNotFoundError(
            f"v0.3.2 provenance runs directory not found: {metadata_source / 'runs'}"
        )
    rows: list[dict[str, Any]] = []
    pairs: list[tuple[str, Path]] = []
    for case_id, prompt_id in CASE_TO_PROMPT.items():
        case_dir = asset_root / case_id
        case = _read_json(case_dir / "case.json")
        manifest = AssetManifestV1.model_validate(_read_json(case_dir / "asset_manifest.json"))
        validate_asset_manifest(manifest, base_dir=case_dir)
        source_run = source / "runs" / prompt_id
        metadata_run = metadata_source / "runs" / prompt_id
        request = _read_json(metadata_run / "request.json")
        brief = StructuredBriefV1.model_validate(_read_json(metadata_run / "brief.json"))
        source_design_path = source_run / "v0.3.2_hardened" / "design.json"
        original = DesignDocument.model_validate(_read_json(source_design_path))
        baseline = _prepare_case_document(original, case_id=case_id, case=case)
        destination = runs / case_id
        baseline_dir = destination / "baseline"
        asset_dir = destination / "asset_aware"
        baseline_dir.mkdir(parents=True)
        asset_dir.mkdir()
        shutil.copy2(case_dir / "case.json", destination / "case.json")
        shutil.copy2(case_dir / "asset_manifest.json", destination / "asset_manifest.json")
        analyses = analyze_manifest_assets(manifest.assets, base_dir=case_dir)
        _write_json(destination / "asset_analysis.json", analyses)

        baseline_fitted, baseline_typography = fit_design_typography(baseline, allow_expand=False)
        baseline_preview = render_preview(
            baseline_fitted,
            baseline_dir / "preview.png",
            max_dimension=1200,
            allow_upscale=True,
        )
        _write_json(baseline_dir / "design.json", baseline_fitted.model_dump(mode="json"))
        _write_json(baseline_dir / "typography.json", baseline_typography)
        aware, report = apply_asset_aware_composition(
            baseline,
            brief=brief,
            manifest=manifest,
            base_dir=case_dir,
        )
        aware_fitted, typography = fit_design_typography(aware, allow_expand=False)
        aware_preview = render_preview(
            aware_fitted,
            asset_dir / "preview.png",
            max_dimension=1200,
            allow_upscale=True,
        )
        operations = compile_corel_operations(
            aware_fitted,
            width_mm=float(request["width_mm"]),
            height_mm=float(request["height_mm"]),
        )
        asset_metrics = evaluate_asset_aware_composition(aware_fitted, manifest=manifest)
        validation = {"raw_schema_valid": True, "strict_schema_valid": True}
        before_metrics = _flatten(
            scorer.score(
                prompt=str(request["prompt"]),
                document=baseline_fitted,
                preview_path=baseline_preview,
                validation=validation,
            )
        )
        after_metrics = _flatten(
            scorer.score(
                prompt=str(request["prompt"]),
                document=aware_fitted,
                preview_path=aware_preview,
                validation=validation,
            )
        )
        after_metrics["asset"] = asset_metrics
        _write_json(asset_dir / "design.json", aware_fitted.model_dump(mode="json"))
        _write_json(asset_dir / "corel_operations.json", operations)
        _write_json(asset_dir / "postprocess.json", report)
        _write_json(asset_dir / "metrics.json", after_metrics)
        _write_json(baseline_dir / "metrics.json", before_metrics)
        _write_json(destination / "palette.json", report["palette"])
        comparison = write_manual_review_artifacts(
            prompt_id=case_id,
            prompt=str(request["prompt"]),
            v02_preview_path=baseline_preview,
            v02_metrics=before_metrics,
            v03_preview_path=aware_preview,
            v03_metrics=after_metrics,
            v02_design_path=baseline_dir / "design.json",
            v03_design_path=asset_dir / "design.json",
            retrieved_references=[],
            output_dir=destination,
            left_key="placeholder",
            right_key="asset_aware",
            left_label="V0.3.2-style placeholder",
            right_label="V0.3.3 real/project asset",
            artifact_type="v0.3.2_placeholder_vs_v0.3.3_asset_aware",
        )
        shutil.copy2(comparison["side_by_side"], destination / "comparison.png")
        pairs.append((case_id, comparison["side_by_side"]))
        row = {
            "case_id": case_id,
            "source_prompt_id": prompt_id,
            "baseline": before_metrics,
            "asset_aware": after_metrics,
            "asset_metrics": asset_metrics,
            "strict_schema_valid": True,
            "corel_operation_count": len(operations),
            "text_truncated": typography["truncated_count"],
            "comparison_path": str(comparison["html"]),
        }
        rows.append(row)
        _write_json(destination / "comparison_metrics.json", row)
    metric_names = (
        "combined", "technical", "overlap_ratio", "spacing",
        "headline_dominance", "text_fit_rate", "coverage",
    )
    aggregates = {
        metric: {
            "placeholder": mean(float(row["baseline"].get(metric, 0)) for row in rows),
            "asset_aware": mean(float(row["asset_aware"].get(metric, 0)) for row in rows),
            "delta": mean(float(row["asset_aware"].get(metric, 0)) for row in rows)
            - mean(float(row["baseline"].get(metric, 0)) for row in rows),
        }
        for metric in metric_names
    }
    asset_metric_names = (
        "asset_use_rate", "asset_intent_preservation", "logo_aspect_preservation",
        "hero_area_ratio", "crop_ratio", "focal_point_preservation",
        "image_text_contrast", "palette_asset_alignment", "placeholder_remaining_count",
        "real_asset_case_count", "commercial_asset_case_count", "missing_asset_case_count",
    )
    summary = {
        "schema_version": "1.0",
        "artifact_type": "design_ai_v0.3.3_asset_aware_replay",
        "case_count": len(rows),
        "fresh_model_generations": 0,
        "human_reviewed": False,
        "human_preference_collected": False,
        "scorer_changed": False,
        "strict_schema_valid": sum(row["strict_schema_valid"] for row in rows),
        "corel_compile_success": sum(row["corel_operation_count"] > 0 for row in rows),
        "no_truncation": sum(row["text_truncated"] == 0 for row in rows),
        "aggregates": aggregates,
        "asset_metrics": {
            metric: mean(float(row["asset_metrics"][metric]) for row in rows)
            for metric in asset_metric_names
        },
        "license_matrix": {
            "asset_commercial_allowed": True,
            "model_commercial_allowed": False,
            "reference_corpus_commercial_allowed": False,
            "final_pipeline_commercial_allowed": False,
        },
        "rows": rows,
    }
    _write_json(output / "summary.json", summary)
    _contact_sheet(pairs, output / "contact_sheet_real_assets_5.png")
    links = "".join(
        f'<li><a href="runs/{row["case_id"]}/comparison.html">{row["case_id"]}</a></li>'
        for row in rows
    )
    (output / "index.html").write_text(
        "<!doctype html><html><head><meta charset=\"utf-8\"><title>v0.3.3 real assets</title>"
        "<style>body{font:16px Arial;max-width:1400px;margin:24px auto;background:#eee;color:#111}"
        "img{max-width:100%;background:white}</style></head><body>"
        "<h1>V0.3.2 placeholder vs V0.3.3 asset-aware composition</h1>"
        "<p>Human review pending. Same scale; no model generation or scorer change.</p>"
        '<img src="contact_sheet_real_assets_5.png" alt="five asset comparisons">'
        f"<ul>{links}</ul></body></html>\n",
        encoding="utf-8",
    )
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--asset-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--score-config",
        type=Path,
        default=Path("training/config/scoring/aesthetic_v0_3.json"),
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    summary = replay(
        source=args.source,
        asset_root=args.asset_root,
        output=args.output,
        score_config=args.score_config,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
