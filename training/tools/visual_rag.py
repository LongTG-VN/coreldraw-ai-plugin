"""Retrieve v0.3.4 hybrid references for a brief and optional asset manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from training.retrieval import (
    HybridReferenceRetriever,
    HybridRetrievalWeights,
    JsonlReferenceProvider,
    TransformersSiglip2Embedder,
    VisualEmbeddingIndex,
    analyze_brief,
    build_reference_context,
)


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _manifest_assets(path: Path | None) -> list[Path]:
    if path is None:
        return []
    manifest_path = path.resolve()
    root = manifest_path.parent
    rows = _read_json(manifest_path).get("assets", [])
    preferred = [
        row for row in rows
        if row.get("role") in {"hero", "product", "background", "illustration"}
    ]
    selected = preferred or [row for row in rows if row.get("role") != "logo"]
    paths = []
    for row in selected[:2]:
        relative = row.get("preview_path") or row.get("path")
        if not relative:
            continue
        asset = (root / relative).resolve()
        if not asset.is_file():
            raise FileNotFoundError(f"asset manifest file missing: {asset}")
        paths.append(asset)
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-index", type=Path, required=True)
    parser.add_argument("--visual-index", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--width", type=float, required=True)
    parser.add_argument("--height", type=float, required=True)
    parser.add_argument("--asset-manifest", type=Path)
    parser.add_argument("--top-k", type=int)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--device", choices=("auto", "cuda", "cpu"), default="auto")
    args = parser.parse_args()
    config = _read_json(args.config.resolve())
    visual_index = VisualEmbeddingIndex(args.visual_index.resolve())
    embedder = TransformersSiglip2Embedder(
        model_id=visual_index.manifest.embedding_model,
        revision=visual_index.manifest.embedding_revision,
        device=args.device,
    )
    retriever = HybridReferenceRetriever(
        JsonlReferenceProvider(args.reference_index.resolve()),
        visual_index=visual_index,
        embedder=embedder,
        weights=HybridRetrievalWeights(**config["weights"]),
        mmr_lambda=float(config["mmr_lambda"]),
    )
    brief = analyze_brief(args.prompt, width=args.width, height=args.height)
    results = retriever.retrieve_references(
        brief,
        top_k=args.top_k or int(config["top_k"]),
        asset_paths=_manifest_assets(args.asset_manifest),
    )
    context = build_reference_context(
        results,
        max_tokens=int(config["context_token_budget"]),
    )
    payload = {
        "schema_version": "1.0",
        "brief": brief.model_dump(mode="json"),
        "references": [row.model_dump(mode="json") for row in results],
        "context": context.model_dump(mode="json"),
        "diagnostics": retriever.last_diagnostics.__dict__,
        "visual_index_fingerprint": visual_index.manifest.fingerprint,
    }
    encoded = json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n"
    if args.output:
        args.output.resolve().parent.mkdir(parents=True, exist_ok=True)
        args.output.resolve().write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
