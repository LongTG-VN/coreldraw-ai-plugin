"""Build the pinned v0.3.4 local SigLIP2 reference embedding index."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from training.retrieval import JsonlReferenceProvider
from training.retrieval.visual_embeddings import (
    TransformersSiglip2Embedder,
    VisualEmbeddingCache,
)
from training.retrieval.visual_index import build_visual_index


def _read_json(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"config root must be an object: {path}")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-index", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("training/config/retrieval/visual_rag_v034.json"),
    )
    parser.add_argument(
        "--cache",
        type=Path,
        default=Path("training/workspace/cache/visual_embeddings/v034"),
    )
    parser.add_argument("--device", choices=("auto", "cuda", "cpu"), default="auto")
    args = parser.parse_args()
    config = _read_json(args.config.resolve())
    embedding = config["embedding"]
    embedder = TransformersSiglip2Embedder(
        model_id=embedding["model_id"],
        revision=embedding["revision"],
        device=args.device,
    )
    reference_index = args.reference_index.resolve()
    result = build_visual_index(
        provider=JsonlReferenceProvider(reference_index),
        source_reference_index=reference_index,
        reference_root=reference_index.parent,
        output=args.output.resolve(),
        embedder=embedder,
        cache=VisualEmbeddingCache(args.cache.resolve()),
    )
    print(
        json.dumps(
            {
                "manifest": result.manifest.model_dump(mode="json"),
                "build_report": result.build_report,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
