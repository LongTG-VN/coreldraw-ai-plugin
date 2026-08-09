from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable

from training.tools.bootstrap import CONFIG_PATH, REPO_ROOT, load_registry


PROBE_ROOT = REPO_ROOT / "training" / "workspace" / "probes"


def _safe_size(image: Any) -> list[int] | None:
    size = getattr(image, "size", None)
    if size and len(size) == 2:
        return [int(size[0]), int(size[1])]
    return None


def _layer_count(layers: Any) -> int:
    if isinstance(layers, list):
        return len(layers)
    if isinstance(layers, dict):
        lengths = [len(value) for value in layers.values() if isinstance(value, list)]
        return max(lengths, default=0)
    return 0


def _first_texts(layers: Any, limit: int = 5) -> list[str]:
    if isinstance(layers, dict):
        values = layers.get("text")
        if isinstance(values, list):
            return [str(value) for value in values[:limit] if value is not None]
    if isinstance(layers, list):
        result: list[str] = []
        for item in layers:
            if isinstance(item, dict) and item.get("text") is not None:
                result.append(str(item["text"]))
                if len(result) >= limit:
                    break
        return result
    return []


def summarize_row(source: str, row: dict[str, Any], index: int) -> dict[str, Any]:
    if source == "genposter100k":
        layers = row.get("layers")
        return {
            "sample_index": index,
            "upstream_id": row.get("id"),
            "canvas_size": _safe_size(row.get("background_image"))
            or _safe_size(row.get("merged_image")),
            "layer_count": _layer_count(layers),
            "sample_texts": _first_texts(layers),
            "region_count": len(row.get("regions") or []),
            "psd_path": row.get("psd_path"),
        }

    if source == "cgl_v2":
        annotations = row.get("annotations") or {}
        annotation_count = 0
        if isinstance(annotations, list):
            annotation_count = len(annotations)
        elif isinstance(annotations, dict):
            ids = annotations.get("annotation_id")
            if isinstance(ids, list):
                annotation_count = len(ids)
        return {
            "sample_index": index,
            "upstream_id": row.get("image_id"),
            "file_name": row.get("file_name"),
            "canvas_size": [row.get("width"), row.get("height")],
            "annotation_count": annotation_count,
            "has_text_annotations": bool(row.get("text_annotations")),
        }

    return {
        "sample_index": index,
        "keys": sorted(row.keys()),
    }


def probe_rows(
    source: str,
    limit: int,
    registry: dict[str, Any],
) -> Iterable[dict[str, Any]]:
    source_config = registry["sources"].get(source)
    if not source_config:
        raise ValueError(f"Unknown source: {source}")
    if source_config.get("kind") != "huggingface":
        raise ValueError(f"Source '{source}' is not a Hugging Face dataset.")

    try:
        from datasets import load_dataset
    except ImportError as exc:
        raise RuntimeError(
            "Missing bootstrap dependency. Install: pip install -r training/requirements.txt"
        ) from exc

    dataset = load_dataset(
        source_config["dataset_id"],
        split=source_config.get("split", "train"),
        streaming=True,
    )
    for index, row in enumerate(dataset):
        if index >= limit:
            break
        summary = summarize_row(source, row, index)
        summary["source"] = source
        summary["dataset_id"] = source_config["dataset_id"]
        summary["license"] = source_config.get("license")
        summary["license_class"] = source_config.get("license_class")
        summary["commercial_allowed"] = bool(
            source_config.get("commercial_allowed", False)
        )
        yield summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Stream a tiny public dataset subset and inspect its schema."
    )
    parser.add_argument("--source", choices=("genposter100k", "cgl_v2"), required=True)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    if args.limit < 1 or args.limit > 500:
        parser.error("--limit must be between 1 and 500 for the probe tool")

    registry = load_registry(CONFIG_PATH)
    source_config = registry["sources"][args.source]
    output = args.output or PROBE_ROOT / f"{args.source}_{args.limit}.jsonl"
    output.parent.mkdir(parents=True, exist_ok=True)

    count = 0
    with output.open("w", encoding="utf-8") as handle:
        for record in probe_rows(args.source, args.limit, registry):
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            count += 1

    result = {
        "source": args.source,
        "dataset_id": source_config["dataset_id"],
        "license_class": source_config.get("license_class"),
        "commercial_allowed": source_config.get("commercial_allowed"),
        "rows_written": count,
        "output": str(output),
        "note": "This is a schema probe, not a production dataset export.",
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
