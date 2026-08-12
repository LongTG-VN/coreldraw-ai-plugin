"""Evaluate frozen v0.3.4 hybrid retrieval before any planner generation."""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Iterable

from PIL import Image, ImageDraw, ImageFont

from training.retrieval import (
    HybridReferenceRetriever,
    HybridRetrievalWeights,
    JsonlReferenceProvider,
    ReferenceRetriever,
    RetrievalLeakageExclusions,
    TransformersSiglip2Embedder,
    VisualEmbeddingIndex,
    analyze_brief,
)
from training.retrieval.models import ReferenceRecordV1
from training.retrieval.visual_embeddings import cosine_similarity, normalize_embedding
from training.retrieval.hybrid import visual_query_text


FINAL_CASE_IDS = (
    "spa", "cafe", "sale", "menu", "signage",
)


@dataclass(frozen=True)
class MemoryProvider:
    records: list[ReferenceRecordV1]
    provider_name: str = "memory_filtered"

    def load_references(self) -> list[ReferenceRecordV1]:
        return list(self.records)


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _mean(rows: Iterable[float]) -> float:
    values = list(rows)
    return mean(values) if values else 0.0


def _asset_paths(case_root: Path) -> list[Path]:
    manifest = _read_json(case_root / "asset_manifest.json")
    preferred = [
        item for item in manifest["assets"]
        if item["role"] in {"hero", "product", "background", "illustration"}
    ]
    if not preferred:
        preferred = [item for item in manifest["assets"] if item["role"] != "logo"]
    if not preferred:
        preferred = manifest["assets"][:1]
    paths = []
    for item in preferred[:2]:
        relative = item.get("preview_path") or item["path"]
        path = (case_root / relative).resolve()
        if path.suffix.lower() == ".svg" and item.get("preview_path"):
            path = (case_root / item["preview_path"]).resolve()
        if path.is_file() and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
            paths.append(path)
    return paths


def _queries(benchmark: Path, asset_root: Path) -> list[dict]:
    prompt_rows = _read_json(benchmark)["prompts"]
    by_id = {row["id"]: row for row in prompt_rows}
    rows = [
        {
            "query_id": row["id"],
            "source": "v0.2_13_prompt_benchmark",
            "prompt": row["prompt"],
            "width": row["width_mm"],
            "height": row["height_mm"],
            "asset_paths": [],
        }
        for row in prompt_rows
    ]
    for case_id in FINAL_CASE_IDS:
        case_root = asset_root / case_id
        case = _read_json(case_root / "case.json")
        source = by_id[case["source_prompt_id"]]
        copy = " ".join(
            str(case[key]) for key in ("headline", "subheadline", "body", "cta")
            if case.get(key)
        )
        rows.append(
            {
                "query_id": f"asset_{case_id}",
                "source": "v0.3.3_real_asset_case",
                "prompt": f"{source['prompt']}. Nội dung benchmark: {copy}",
                "width": source["width_mm"],
                "height": source["height_mm"],
                "asset_paths": _asset_paths(case_root),
            }
        )
    return rows


def _filtered(records: list[ReferenceRecordV1], mode: str, category: str) -> list[ReferenceRecordV1]:
    if mode == "full":
        return records
    if mode == "exclude_exact_category_templates":
        return [
            row for row in records
            if not (row.metadata.source == "synthetic_owned" and row.metadata.category == category)
        ]
    if mode == "genposter_only":
        return [row for row in records if row.metadata.source == "genposter100k"]
    if mode == "leave_one_template_family_out":
        return [
            row for row in records
            if not (row.metadata.source == "synthetic_owned" and row.metadata.category == category)
        ]
    raise ValueError(f"unknown held-out mode: {mode}")


def _visual_scores(reference_ids: list[str], query_vector: list[float], index: VisualEmbeddingIndex) -> list[float]:
    return [
        max(0.0, min(1.0, (cosine_similarity(query_vector, index.vector(reference_id)) + 1.0) / 2.0))
        for reference_id in reference_ids
    ]


def _metrics(results, *, visual_scores: list[float] | None = None) -> dict:
    sources = {item.metadata.source for item in results}
    families = {
        getattr(item, "template_family", item.reference_id)
        for item in results
    }
    structural_relevance = _mean(
        getattr(item, "structural_score", item.match.relevance) for item in results
    )
    visual_relevance = _mean(
        visual_scores if visual_scores is not None
        else (item.visual_text_score for item in results)
    )
    visual_asset_values = [
        item.visual_asset_score for item in results
        if getattr(item, "visual_asset_score", None) is not None
    ]
    return {
        "result_count": len(results),
        "structural_relevance": structural_relevance,
        "category_accuracy": _mean(item.match.category for item in results),
        "format_accuracy": _mean(item.match.format for item in results),
        "diversity": _mean(item.match.diversity for item in results),
        "visual_relevance": visual_relevance,
        "visual_asset_similarity": _mean(visual_asset_values),
        "hybrid_relevance": _mean(
            getattr(item, "hybrid_score", 0.0) for item in results
        ),
        "retrieval_quality": .5 * structural_relevance + .5 * visual_relevance,
        "source_diversity": len(sources) / max(1, len(results)),
        "template_family_diversity": len(families) / max(1, len(results)),
        "research_only_count": sum(item.metadata.research_only for item in results),
    }


def _font(size: int):
    for path in ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/segoeui.ttf"):
        if Path(path).is_file():
            return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()


def _preview(reference_root: Path, item, size=(240, 160)) -> Image.Image:
    path = (reference_root / item.metadata.preview_path).resolve()
    image = Image.open(path).convert("RGB")
    image.thumbnail(size, Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", size, "#f4f1eb")
    canvas.paste(image, ((size[0] - image.width) // 2, (size[1] - image.height) // 2))
    return canvas


def _strip(reference_root: Path, title: str, results) -> Image.Image:
    cell_w, cell_h = 250, 220
    sheet = Image.new("RGB", (cell_w * 5, cell_h), "white")
    draw = ImageDraw.Draw(sheet)
    title_font, label_font = _font(18), _font(13)
    for index, item in enumerate(results):
        x = index * cell_w
        sheet.paste(_preview(reference_root, item), (x + 5, 30))
        draw.text((x + 5, 5), title if index == 0 else "", fill="#111111", font=title_font)
        label = f"{index + 1}. {item.reference_id}\ncat={item.metadata.category} score={item.score:.3f}"
        draw.multiline_text((x + 5, 193), label, fill="#222222", font=label_font, spacing=2)
    return sheet


def _write_review(root: Path, reference_root: Path, query: dict, structural, hybrid, payload: dict) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    structural_sheet = _strip(reference_root, "STRUCTURAL TOP-5", structural)
    hybrid_sheet = _strip(reference_root, "HYBRID VISUAL TOP-5", hybrid)
    structural_path = root / "structural_top5.png"
    hybrid_path = root / "hybrid_top5.png"
    structural_sheet.save(structural_path)
    hybrid_sheet.save(hybrid_path)
    comparison = Image.new("RGB", (structural_sheet.width, structural_sheet.height * 2 + 70), "#ddd8cf")
    comparison.paste(structural_sheet, (0, 35))
    comparison.paste(hybrid_sheet, (0, structural_sheet.height + 70))
    draw = ImageDraw.Draw(comparison)
    draw.text((12, 7), query["query_id"], fill="#111111", font=_font(22))
    comparison_path = root / "comparison.png"
    comparison.save(comparison_path)
    (root / "query.json").write_text(json.dumps(query, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    (root / "retrieval.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    html = f"""<!doctype html><meta charset=\"utf-8\"><title>{query['query_id']}</title>
<style>body{{font-family:Arial;background:#eee;padding:24px}}img{{max-width:100%;background:white}}</style>
<h1>{query['query_id']}</h1><p>{query['prompt']}</p><img src=\"comparison.png\"><pre>{json.dumps(payload['metrics'], ensure_ascii=False, indent=2)}</pre>"""
    (root / "comparison.html").write_text(html, encoding="utf-8")
    return comparison_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-index", type=Path, required=True)
    parser.add_argument("--visual-index", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--benchmark", type=Path, required=True)
    parser.add_argument("--asset-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--device", choices=("auto", "cuda", "cpu"), default="auto")
    args = parser.parse_args()
    started = time.perf_counter()
    config = _read_json(args.config.resolve())
    output = args.output.resolve()
    review_root = output / "retrieval_review"
    output.mkdir(parents=True, exist_ok=True)
    base_provider = JsonlReferenceProvider(args.reference_index.resolve())
    all_records = base_provider.load_references()
    visual_index = VisualEmbeddingIndex(args.visual_index.resolve())
    embedder = TransformersSiglip2Embedder(
        model_id=visual_index.manifest.embedding_model,
        revision=visual_index.manifest.embedding_revision,
        device=args.device,
    )
    weights = HybridRetrievalWeights(**config["weights"])
    modes = ("full", "exclude_exact_category_templates", "genposter_only", "leave_one_template_family_out")
    queries = _queries(args.benchmark.resolve(), args.asset_root.resolve())
    rows, comparison_paths = [], []
    for query in queries:
        brief = analyze_brief(query["prompt"], width=query["width"], height=query["height"])
        query_vector = normalize_embedding(embedder.embed_text(visual_query_text(brief)))
        mode_rows = {}
        for mode in modes:
            records = _filtered(all_records, mode, brief.category)
            provider = MemoryProvider(records)
            structural_started = time.perf_counter()
            structural = ReferenceRetriever(provider).retrieve_references(brief, top_k=5)
            structural_latency = time.perf_counter() - structural_started
            allowed_ids = {row.metadata.reference_id for row in records}
            exclusions = RetrievalLeakageExclusions(
                reference_ids=frozenset(
                    record.metadata.reference_id for record in all_records
                    if record.metadata.reference_id not in allowed_ids
                ),
                near_duplicate_threshold=config["near_duplicate_threshold"],
            )
            hybrid_retriever = HybridReferenceRetriever(
                base_provider,
                visual_index=visual_index,
                embedder=embedder,
                weights=weights,
                mmr_lambda=config["mmr_lambda"],
            )
            hybrid = hybrid_retriever.retrieve_references(
                brief,
                top_k=5,
                asset_paths=query["asset_paths"],
                exclusions=exclusions,
            )
            structural_visual = _visual_scores(
                [item.reference_id for item in structural], query_vector, visual_index
            )
            mode_rows[mode] = {
                "structural": [item.model_dump(mode="json") for item in structural],
                "hybrid": [item.model_dump(mode="json") for item in hybrid],
                "metrics": {
                    "structural": _metrics(structural, visual_scores=structural_visual),
                    "hybrid": _metrics(hybrid),
                    "structural_latency_seconds": structural_latency,
                    "hybrid_latency_seconds": hybrid_retriever.last_diagnostics.retrieval_latency_seconds,
                    "embedding_latency_seconds": hybrid_retriever.last_diagnostics.embedding_latency_seconds,
                    "near_duplicate_rejections": hybrid_retriever.last_diagnostics.near_duplicate_rejection_count,
                },
            }
        row = {
            "query_id": query["query_id"],
            "source": query["source"],
            "brief": brief.model_dump(mode="json"),
            "asset_paths": [str(path) for path in query["asset_paths"]],
            "modes": mode_rows,
        }
        rows.append(row)
        review_payload = {"metrics": mode_rows["full"]["metrics"], "human_preference_collected": False}
        comparison_paths.append(
            _write_review(
                review_root / query["query_id"],
                args.reference_index.resolve().parent,
                query,
                ReferenceRetriever(base_provider).retrieve_references(brief, top_k=5),
                HybridReferenceRetriever(base_provider, visual_index=visual_index, embedder=embedder, weights=weights, mmr_lambda=config["mmr_lambda"]).retrieve_references(brief, top_k=5, asset_paths=query["asset_paths"]),
                review_payload,
            )
        )
    def aggregate(method: str, mode: str, key: str) -> float:
        return _mean(row["modes"][mode]["metrics"][method][key] for row in rows)
    summary_modes = {}
    for mode in modes:
        summary_modes[mode] = {
            method: {
                key: aggregate(method, mode, key)
                for key in (
                    "structural_relevance", "visual_relevance",
                    "visual_asset_similarity", "hybrid_relevance",
                    "retrieval_quality", "category_accuracy", "format_accuracy",
                    "diversity", "source_diversity", "template_family_diversity",
                )
            }
            for method in ("structural", "hybrid")
        }
    full_structural = summary_modes["full"]["structural"]
    full_hybrid = summary_modes["full"]["hybrid"]
    full_quality_improved = (
        full_hybrid["retrieval_quality"] > full_structural["retrieval_quality"]
    )
    held_out_quality_improved = (
        summary_modes["exclude_exact_category_templates"]["hybrid"]["retrieval_quality"]
        > summary_modes["exclude_exact_category_templates"]["structural"]["retrieval_quality"]
    )
    meaningful_visual_gain = (
        full_hybrid["visual_relevance"] - full_structural["visual_relevance"] >= .01
    )
    summary = {
        "schema_version": "1.0",
        "benchmark_id": "design_ai_v0.3.4_hybrid_visual_rag_retrieval",
        "query_count": len(rows),
        "brief_only_count": sum(not row["asset_paths"] for row in rows),
        "brief_plus_asset_count": sum(bool(row["asset_paths"]) for row in rows),
        "model": visual_index.manifest.embedding_model,
        "revision": visual_index.manifest.embedding_revision,
        "visual_index_id": visual_index.manifest.visual_index_id,
        "visual_index_fingerprint": visual_index.manifest.fingerprint,
        "frozen_weights": config["weights"],
        "modes": summary_modes,
        "full_corpus_delta": {
            key: full_hybrid[key] - full_structural[key]
            for key in full_hybrid
        },
        "gates": {
            "full_retrieval_quality_improved": full_quality_improved,
            "held_out_retrieval_quality_improved": held_out_quality_improved,
            "meaningful_visual_gain": meaningful_visual_gain,
            "retrieval_credible_for_generation": (
                full_quality_improved and held_out_quality_improved and meaningful_visual_gain
            ),
        },
        "human_preference_collected": False,
        "model_load_seconds": embedder.load_duration_seconds,
        "peak_memory_gib": embedder.peak_memory_gib,
        "duration_seconds": time.perf_counter() - started,
    }
    rows_json = json.dumps(rows, ensure_ascii=False, indent=2) + "\n"
    summary_json = json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
    for name in ("retrieval_rows.json", "benchmark_rows.json"):
        (output / name).write_text(rows_json, encoding="utf-8")
    for name in ("retrieval_summary.json", "benchmark_summary.json"):
        (output / name).write_text(summary_json, encoding="utf-8")
    images = [Image.open(path).convert("RGB") for path in comparison_paths]
    width = max(image.width for image in images)
    contact = Image.new("RGB", (width, sum(image.height for image in images)), "white")
    y = 0
    for image in images:
        contact.paste(image, (0, y)); y += image.height
    contact.save(output / "retrieval_contact_sheet_all.png")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
