"""Deterministic side-by-side artifacts for an explicitly pending human review."""

from __future__ import annotations

import html
import json
import math
import shutil
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, UnidentifiedImageError


REVIEW_DIMENSIONS = ("overall", "hierarchy", "typography", "composition")


def _require_text(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _png_path(value: str | Path, field: str) -> Path:
    path = Path(value).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"{field} does not exist: {path}")
    try:
        with Image.open(path) as image:
            if image.format != "PNG":
                raise ValueError(f"{field} must be a PNG image: {path}")
            image.verify()
    except UnidentifiedImageError as exc:
        raise ValueError(f"{field} is not a readable image: {path}") from exc
    return path


def _optional_json_path(value: str | Path | None, field: str) -> Path | None:
    if value is None:
        return None
    path = Path(value).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"{field} does not exist: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{field} is not valid JSON: {path}") from exc
    if not isinstance(payload, Mapping):
        raise ValueError(f"{field} JSON root must be an object: {path}")
    return path


def _json_value(value: Any, field: str) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{field} contains a non-finite number")
        return value
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"{field} keys must be strings")
            result[key] = _json_value(item, f"{field}.{key}")
        return result
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_json_value(item, f"{field}[{index}]") for index, item in enumerate(value)]
    raise ValueError(f"{field} contains a non-JSON value: {type(value).__name__}")


def _metrics(value: Mapping[str, Any], field: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be a mapping")
    return _json_value(value, field)


def _references(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if isinstance(records, (str, bytes, bytearray)) or not isinstance(records, Sequence):
        raise ValueError("retrieved_references must be a sequence")
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, record in enumerate(records):
        if not isinstance(record, Mapping):
            raise ValueError(f"retrieved_references[{index}] must be a mapping")
        item = _json_value(record, f"retrieved_references[{index}]")
        reference_id = _require_text(
            item.get("reference_id"), f"retrieved_references[{index}].reference_id"
        )
        if reference_id in seen:
            raise ValueError(f"duplicate reference_id: {reference_id}")
        seen.add(reference_id)
        item["reference_id"] = reference_id
        if "score" in item:
            score = item["score"]
            if isinstance(score, bool) or not isinstance(score, (int, float)):
                raise ValueError(f"retrieved_references[{index}].score must be numeric")
            if not 0 <= float(score) <= 1:
                raise ValueError(f"retrieved_references[{index}].score must be in 0..1")
        for path_field in ("preview_path", "design_document_path"):
            path_value = item.get(path_field)
            if path_value is None:
                continue
            path = Path(path_value).expanduser().resolve()
            if not path.is_file():
                raise FileNotFoundError(
                    f"retrieved_references[{index}].{path_field} does not exist: {path}"
                )
            item[path_field] = str(path)
        normalized.append(item)
    return normalized


def _render_side_by_side(
    left_path: Path,
    right_path: Path,
    output_path: Path,
    *,
    labels: tuple[str, str] = ("V0.2", "V0.3 RAG"),
) -> None:
    previews: list[Image.Image] = []
    try:
        for path in (left_path, right_path):
            with Image.open(path) as source:
                image = source.convert("RGB")
                image.thumbnail((720, 720), Image.Resampling.LANCZOS)
                previews.append(image.copy())
        padding = 24
        label_height = 42
        panel_width = max(image.width for image in previews)
        panel_height = max(image.height for image in previews)
        canvas = Image.new(
            "RGB",
            (padding * 3 + panel_width * 2, padding * 2 + label_height + panel_height),
            "white",
        )
        draw = ImageDraw.Draw(canvas)
        for index, (label, image) in enumerate(zip(labels, previews)):
            panel_x = padding + index * (panel_width + padding)
            image_x = panel_x + (panel_width - image.width) // 2
            image_y = padding + label_height + (panel_height - image.height) // 2
            draw.text((panel_x, padding), label, fill="black")
            canvas.paste(image, (image_x, image_y))
        canvas.save(output_path, format="PNG", optimize=False)
    finally:
        for image in previews:
            image.close()


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_manual_review_artifacts(
    *,
    prompt_id: str,
    prompt: str,
    v02_preview_path: str | Path,
    v02_metrics: Mapping[str, Any],
    v03_preview_path: str | Path,
    v03_metrics: Mapping[str, Any],
    v02_design_path: str | Path | None = None,
    v03_design_path: str | Path | None = None,
    retrieved_references: Sequence[Mapping[str, Any]],
    output_dir: str | Path,
    left_key: str = "v0.2",
    right_key: str = "v0.3",
    left_label: str = "Design AI v0.2 best-of-4 winner",
    right_label: str = "Design AI v0.3 RAG best-of-4 winner",
    artifact_type: str = "v0.2_vs_v0.3_design_comparison",
) -> dict[str, Path]:
    """Write a comparison package without asserting or fabricating human judgment."""

    normalized_prompt_id = _require_text(prompt_id, "prompt_id")
    normalized_prompt = _require_text(prompt, "prompt")
    normalized_left_key = _require_text(left_key, "left_key")
    normalized_right_key = _require_text(right_key, "right_key")
    if normalized_left_key == normalized_right_key:
        raise ValueError("comparison variant keys must be distinct")
    normalized_left_label = _require_text(left_label, "left_label")
    normalized_right_label = _require_text(right_label, "right_label")
    normalized_artifact_type = _require_text(artifact_type, "artifact_type")
    v02_preview = _png_path(v02_preview_path, "v02_preview_path")
    v03_preview = _png_path(v03_preview_path, "v03_preview_path")
    v02_design = _optional_json_path(v02_design_path, "v02_design_path")
    v03_design = _optional_json_path(v03_design_path, "v03_design_path")
    normalized_v02_metrics = _metrics(v02_metrics, "v02_metrics")
    normalized_v03_metrics = _metrics(v03_metrics, "v03_metrics")
    normalized_references = _references(retrieved_references)

    destination = Path(output_dir).expanduser().resolve()
    if destination.exists() and not destination.is_dir():
        raise ValueError(f"output_dir is not a directory: {destination}")
    destination.mkdir(parents=True, exist_ok=True)
    preview_dir = destination / "reference_previews"
    for index, record in enumerate(normalized_references, start=1):
        source_value = record.get("preview_path")
        if source_value is None:
            continue
        preview_dir.mkdir(exist_ok=True)
        source = Path(source_value)
        local_name = f"ref_{index:02d}.png"
        shutil.copy2(source, preview_dir / local_name)
        record["local_preview_path"] = f"reference_previews/{local_name}"
    paths = {
        "comparison": destination / "comparison.json",
        "side_by_side": destination / "side_by_side.png",
        "html": destination / "comparison.html",
        "manual_review_template": destination / "manual_review.template.json",
    }

    comparison = {
        "schema_version": "1.0",
        "artifact_type": normalized_artifact_type,
        "prompt_id": normalized_prompt_id,
        "prompt": normalized_prompt,
        "variants": {
            normalized_left_key: {
                "label": normalized_left_label,
                "preview_path": str(v02_preview),
                "design_path": str(v02_design) if v02_design else None,
                "metrics": normalized_v02_metrics,
            },
            normalized_right_key: {
                "label": normalized_right_label,
                "preview_path": str(v03_preview),
                "design_path": str(v03_design) if v03_design else None,
                "metrics": normalized_v03_metrics,
            },
        },
        "retrieved_references": normalized_references,
        "review_state": {
            "human_reviewed": False,
            "preferred": None,
            "heuristic_metrics_are_human_scores": False,
        },
    }
    review_scores = {dimension: None for dimension in REVIEW_DIMENSIONS}
    review_template = {
        "schema_version": "1.0",
        "artifact_type": "manual_design_review_template",
        "prompt_id": normalized_prompt_id,
        "prompt": normalized_prompt,
        "review_status": "pending",
        "preferred": None,
        "scores": {
            normalized_left_key: dict(review_scores),
            normalized_right_key: dict(review_scores),
        },
        "reviewer": None,
        "notes": None,
        "provenance": {
            "human_reviewed": False,
            "selection_source": None,
            "heuristic_metrics_are_human_scores": False,
        },
    }

    _write_json(paths["comparison"], comparison)
    _render_side_by_side(
        v02_preview,
        v03_preview,
        paths["side_by_side"],
        labels=(normalized_left_label, normalized_right_label),
    )
    reference_rows = "".join(
        "<li><code>"
        + html.escape(str(record["reference_id"]))
        + "</code> — score "
        + html.escape(str(record.get("score", "n/a")))
        + (
            '<br><img style="max-width:220px;max-height:180px" src="'
            + html.escape(str(record["local_preview_path"]))
            + '" alt="Retrieved structural reference">'
            if record.get("local_preview_path")
            else ""
        )
        + "</li>"
        for record in normalized_references
    ) or "<li>No references recorded.</li>"
    paths["html"].write_text(
        "<!doctype html>\n"
        '<html lang="en"><head><meta charset="utf-8">'
        "<title>Design comparison</title>"
        "<style>body{font-family:Arial,sans-serif;max-width:1500px;margin:2rem auto;"
        "padding:0 1rem}img{max-width:100%;height:auto}code{font-size:.9em}"
        ".pending{padding:.75rem;background:#fff4cc;border:1px solid #c99b00}</style>"
        "</head><body>"
        f"<h1>{html.escape(normalized_prompt_id)}</h1>"
        f"<p>{html.escape(normalized_prompt)}</p>"
        '<p class="pending"><strong>Human review pending.</strong> '
        "Heuristic metrics below are not human preferences or human scores.</p>"
        '<img src="side_by_side.png" alt="V0.2 and V0.3 RAG winners side by side">'
        "<h2>Retrieved references</h2><ul>"
        f"{reference_rows}</ul>"
        "<h2>Machine metrics</h2>"
        f"<h3>{html.escape(normalized_left_label)}</h3><pre>{html.escape(json.dumps(normalized_v02_metrics, ensure_ascii=False, indent=2, sort_keys=True))}</pre>"
        f"<h3>{html.escape(normalized_right_label)}</h3><pre>{html.escape(json.dumps(normalized_v03_metrics, ensure_ascii=False, indent=2, sort_keys=True))}</pre>"
        "</body></html>\n",
        encoding="utf-8",
    )
    _write_json(paths["manual_review_template"], review_template)
    return paths


__all__ = ["REVIEW_DIMENSIONS", "write_manual_review_artifacts"]
