"""Compare clean v0.3 and v0.3.1 winners without rescoring either release."""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from statistics import mean
from typing import Any

from PIL import Image, ImageDraw

from training.evaluation.manual_review import write_manual_review_artifacts


METRICS = {
    "combined": "combined_score",
    "technical": "technical_score",
    "overlap": "overlap",
    "spacing": "spacing",
    "hierarchy": "hierarchy",
    "text_fit": "text_fit",
    "coverage": "coverage",
    "outside_canvas": "outside_canvas",
    "schema_validity": "schema_valid",
}


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _rows(root: Path) -> dict[str, dict[str, Any]]:
    payload = _read(root / "benchmark_rows.json")
    if not isinstance(payload, list) or not payload:
        raise ValueError(f"benchmark_rows.json must contain rows: {root}")
    result: dict[str, dict[str, Any]] = {}
    for row in payload:
        prompt_id = str(row["prompt_id"])
        if prompt_id in result:
            raise ValueError(f"duplicate prompt_id: {prompt_id}")
        result[prompt_id] = row
    return result


def _contact_sheet(paths: list[tuple[str, Path]], output: Path) -> None:
    panels: list[tuple[str, Image.Image]] = []
    try:
        for label, path in paths:
            with Image.open(path) as source:
                image = source.convert("RGB")
                image.thumbnail((1440, 560), Image.Resampling.LANCZOS)
                panels.append((label, image.copy()))
        width = max((image.width for _, image in panels), default=800) + 40
        height = sum(image.height + 54 for _, image in panels) + 20
        canvas = Image.new("RGB", (width, height), "#F4F4F4")
        draw = ImageDraw.Draw(canvas)
        y = 16
        for label, image in panels:
            draw.text((20, y), label, fill="black")
            y += 30
            canvas.paste(image, ((width - image.width) // 2, y))
            y += image.height + 24
        canvas.save(output, format="PNG", optimize=False)
    finally:
        for _, image in panels:
            image.close()


def _references(run_dir: Path) -> list[dict[str, Any]]:
    payload = _read(run_dir / "retrieval.json")
    return [
        {
            "reference_id": item["reference_id"],
            "score": item["score"],
            "match": item["match"],
        }
        for item in payload.get("results", [])
    ]


def compare(*, v03: Path, v031: Path, output: Path) -> dict[str, Any]:
    v03 = v03.resolve()
    v031 = v031.resolve()
    output = output.resolve()
    old_rows = _rows(v03)
    new_rows = _rows(v031)
    if set(old_rows) != set(new_rows):
        raise ValueError("v0.3 and v0.3.1 prompt IDs differ")
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"comparison output must be new or empty: {output}")
    output.mkdir(parents=True, exist_ok=True)
    runs = output / "runs"
    runs.mkdir()

    comparison_rows: list[dict[str, Any]] = []
    contact_paths: list[tuple[str, Path]] = []
    for prompt_id in sorted(old_rows):
        old_row = old_rows[prompt_id]
        new_row = new_rows[prompt_id]
        if old_row["prompt"] != new_row["prompt"]:
            raise ValueError(f"prompt text differs for {prompt_id}")
        old = old_row["v0.3"]
        new = new_row["v0.3"]
        old_metrics = dict(old["winner_metrics"])
        new_metrics = dict(new["winner_metrics"])
        destination = runs / prompt_id
        artifacts = write_manual_review_artifacts(
            prompt_id=prompt_id,
            prompt=str(old_row["prompt"]),
            v02_preview_path=old["winner_preview_path"],
            v02_metrics=old_metrics,
            v03_preview_path=new["winner_preview_path"],
            v03_metrics=new_metrics,
            v02_design_path=old["winner_design_path"],
            v03_design_path=new["winner_design_path"],
            retrieved_references=_references(Path(new["run_dir"])),
            output_dir=destination,
            left_key="v0.3",
            right_key="v0.3.1",
            left_label="V0.3 clean winner",
            right_label="V0.3.1 clean visual winner",
            artifact_type="v0.3_vs_v0.3.1_clean_comparison",
        )
        contact_paths.append((prompt_id, artifacts["side_by_side"]))
        row = {
            "prompt_id": prompt_id,
            "prompt": old_row["prompt"],
            "v0.3": old_metrics,
            "v0.3.1": new_metrics,
            "v0.3_winner": old["winner"],
            "v0.3.1_winner": new["winner"],
            "v0.3.1_candidate_diversity": new["candidate_diversity"],
            "comparison_path": str(artifacts["html"]),
            "human_reviewed": False,
        }
        comparison_rows.append(row)
        _write(destination / "clean_comparison.json", row)

    aggregates: dict[str, dict[str, float]] = {}
    for label, key in METRICS.items():
        old_average = mean(float(row["v0.3"][key]) for row in comparison_rows)
        new_average = mean(float(row["v0.3.1"][key]) for row in comparison_rows)
        aggregates[label] = {
            "v0.3": old_average,
            "v0.3.1": new_average,
            "delta": new_average - old_average,
        }
    old_combined = aggregates["combined"]["v0.3"]
    improvement = (
        (aggregates["combined"]["v0.3.1"] - old_combined) / old_combined * 100
        if old_combined
        else 0.0
    )
    new_summary = _read(v031 / "benchmark_summary.json")
    provenance = new_summary.get("candidate_provenance", {})
    summary = {
        "schema_version": "1.0",
        "artifact_type": "v0.3_vs_v0.3.1_clean_summary",
        "v0.3_source": str(v03),
        "v0.3.1_source": str(v031),
        "prompt_count": len(comparison_rows),
        "fresh_candidates": provenance.get(
            "fresh_generation_count", new_summary.get("fresh_rag_candidate_count")
        ),
        "resumed_verified_candidates": provenance.get("resumed_verified_candidate_count", 0),
        "unsafe_reused_candidates": provenance.get("raw_cache_reuse_count", 0),
        "combined_improvement_percent": improvement,
        "aggregates": aggregates,
        "human_reviewed": False,
        "human_preference_collected": False,
        "scorer_changed": False,
    }
    _write(output / "comparison_rows.json", comparison_rows)
    _write(output / "comparison_summary.json", summary)
    _contact_sheet(contact_paths, output / "contact_sheet_all_13.png")
    links = "".join(
        f'<li><a href="runs/{html.escape(row["prompt_id"])}/comparison.html">'
        f'{html.escape(row["prompt_id"])}</a></li>'
        for row in comparison_rows
    )
    (output / "index.html").write_text(
        "<!doctype html><html><head><meta charset=\"utf-8\"><title>v0.3 vs v0.3.1 clean</title></head>"
        "<body><h1>V0.3 clean vs V0.3.1 clean</h1>"
        "<p>Human review pending; heuristic scores are not human preference.</p>"
        '<p><img src="contact_sheet_all_13.png" style="max-width:100%"></p>'
        f"<ul>{links}</ul></body></html>\n",
        encoding="utf-8",
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v03", type=Path, required=True)
    parser.add_argument("--v031", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(compare(v03=args.v03, v031=args.v031, output=args.output), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
