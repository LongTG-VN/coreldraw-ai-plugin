"""Regenerate v0.3 manual comparison HTML with retrieved reference previews."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from training.evaluation.manual_review import write_manual_review_artifacts


def refresh_reports(benchmark_root: Path, reference_index: Path) -> int:
    root = benchmark_root.resolve()
    rows_path = root / "benchmark_rows.json"
    if not rows_path.is_file():
        rows_path = root / "benchmark_rows.partial.json"
    rows = json.loads(rows_path.read_text(encoding="utf-8"))
    reference_root = reference_index.resolve().parent
    refreshed = 0
    for row in rows:
        run_dir = Path(row["v0.3"]["run_dir"])
        retrieval = json.loads((run_dir / "retrieval.json").read_text(encoding="utf-8"))
        references = []
        for item in retrieval["results"]:
            metadata = item["metadata"]
            references.append(
                {
                    "reference_id": item["reference_id"],
                    "score": item["score"],
                    "match": item["match"],
                    "category": metadata["category"],
                    "format": metadata["format"],
                    "source": metadata["source"],
                    "license": metadata["license"],
                    "license_class": metadata["license_class"],
                    "research_only": metadata["research_only"],
                    "commercial_allowed": metadata["commercial_allowed"],
                    "preview_path": str(
                        (reference_root / metadata["preview_path"]).resolve()
                    ),
                    "design_document_path": str(
                        (reference_root / metadata["design_document_path"]).resolve()
                    ),
                }
            )
        write_manual_review_artifacts(
            prompt_id=row["prompt_id"],
            prompt=row["prompt"],
            v02_preview_path=row["v0.2"]["winner_preview_path"],
            v02_metrics=row["v0.2"]["winner_metrics"],
            v03_preview_path=row["v0.3"]["winner_preview_path"],
            v03_metrics=row["v0.3"]["winner_metrics"],
            retrieved_references=references,
            output_dir=run_dir,
        )
        refreshed += 1
    return refreshed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--benchmark-root", type=Path, required=True)
    parser.add_argument("--reference-index", type=Path, required=True)
    args = parser.parse_args()
    count = refresh_reports(args.benchmark_root, args.reference_index)
    print(json.dumps({"status": "success", "refreshed_reports": count}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
