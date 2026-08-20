"""Sanitized visual artifacts for private mutation-pilot review."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for candidate in ("arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _approved_preview(path_value: str, workspace: Path) -> Path:
    path = Path(path_value).expanduser().resolve()
    root = workspace.expanduser().resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError("preview escapes mutation-pilot workspace") from exc
    if path.suffix.casefold() not in {".png", ".jpg", ".jpeg"} or not path.is_file():
        raise ValueError("preview is missing or unsupported")
    return path


def _fit(image: Image.Image, width: int, height: int) -> Image.Image:
    copy = image.convert("RGB")
    copy.thumbnail((width, height), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (width, height), "white")
    canvas.paste(copy, ((width - copy.width) // 2, (height - copy.height) // 2))
    return canvas


def build_mutation_review_artifacts(
    *,
    pilot_workspace: Path,
    output_root: Path,
    state_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build same-scale before/after sheets without copying CDRs or paths."""

    workspace = pilot_workspace.resolve()
    output = output_root.resolve()
    comparisons = output / "comparisons"
    sheets = output / "contact_sheets"
    comparisons.mkdir(parents=True, exist_ok=True)
    sheets.mkdir(parents=True, exist_ok=True)
    manifest_rows: list[dict[str, Any]] = []
    comparison_paths: list[Path] = []
    included_results = {"AUTO_SUCCESS", "SUCCESS_WITH_WARNING", "NEEDS_REVIEW"}
    for index, state_row in enumerate(state_rows, start=1):
        result = state_row["result"]
        if result.get("result") not in included_results:
            continue
        if not result.get("preview_before") or not result.get("preview_after"):
            continue
        before = _approved_preview(str(result["preview_before"]), workspace)
        after = _approved_preview(str(result["preview_after"]), workspace)
        operator_id = f"OP_{index:04d}"
        with Image.open(before) as before_image, Image.open(after) as after_image:
            panel_w, panel_h, header = 900, 900, 70
            canvas = Image.new("RGB", (panel_w * 2, panel_h + header), "#e8e8e8")
            canvas.paste(_fit(before_image, panel_w, panel_h), (0, header))
            canvas.paste(_fit(after_image, panel_w, panel_h), (panel_w, header))
            draw = ImageDraw.Draw(canvas)
            title_font = _font(28)
            draw.text((20, 18), f"{operator_id}  BEFORE", fill="black", font=title_font)
            draw.text((panel_w + 20, 18), "AFTER", fill="black", font=title_font)
            comparison_path = comparisons / f"{operator_id}.jpg"
            canvas.save(comparison_path, quality=94, subsampling=0)
        comparison_paths.append(comparison_path)
        manifest_rows.append(
            {
                "operator_id": operator_id,
                "source_token": result["source_token"],
                "comparison_file": f"comparisons/{comparison_path.name}",
                "result": result["result"],
                "object_count_before": result.get("object_count_before"),
                "object_count_after": result.get("object_count_after"),
                "editability_verified": bool(result.get("editability_verified")),
                "source_unchanged": bool(result.get("source_unchanged")),
                "visual_qa_status": result.get("metadata", {})
                .get("visual_qa", {})
                .get("status", ""),
                "visual_qa_issues": "|".join(
                    str(issue)
                    for issue in result.get("metadata", {})
                    .get("visual_qa", {})
                    .get("issues", [])
                ),
            }
        )

    contact_sheet_paths: list[Path] = []
    per_sheet = 4
    for sheet_index, start in enumerate(range(0, len(comparison_paths), per_sheet), start=1):
        group = comparison_paths[start : start + per_sheet]
        sheet = Image.new("RGB", (1800, len(group) * 970), "#303030")
        for row_index, comparison_path in enumerate(group):
            with Image.open(comparison_path) as comparison:
                sheet.paste(comparison.convert("RGB"), (0, row_index * 970))
        sheet_path = sheets / f"contact_sheet_{sheet_index:03d}.jpg"
        sheet.save(sheet_path, quality=92, subsampling=0)
        contact_sheet_paths.append(sheet_path)

    manifest = output / "manifest.csv"
    fieldnames = [
        "operator_id",
        "source_token",
        "comparison_file",
        "result",
        "object_count_before",
        "object_count_after",
        "editability_verified",
        "source_unchanged",
        "visual_qa_status",
        "visual_qa_issues",
    ]
    with manifest.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(manifest_rows)
    summary = {
        "artifact_name": "chatgpt-corel-operator-mutation-pilot-001",
        "comparison_count": len(comparison_paths),
        "auto_success_comparison_count": sum(
            row["result"] in {"AUTO_SUCCESS", "SUCCESS_WITH_WARNING"}
            for row in manifest_rows
        ),
        "needs_review_comparison_count": sum(
            row["result"] == "NEEDS_REVIEW" for row in manifest_rows
        ),
        "contact_sheet_count": len(contact_sheet_paths),
        "cdr_files_included": 0,
        "sqlite_files_included": 0,
        "source_paths_included": 0,
        "human_preference_collected": False,
        "gold_certification": "NONE",
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def validate_private_artifact(root: Path) -> dict[str, int]:
    files = [path for path in root.rglob("*") if path.is_file()]
    forbidden_binary = sum(path.suffix.casefold() in {".cdr", ".cdt", ".sqlite"} for path in files)
    leaks = 0
    needles = ("C:\\", "Users\\Admin", "Downloads\\", "training\\workspace")
    for path in files:
        if path.suffix.casefold() not in {".csv", ".json", ".md", ".txt"}:
            continue
        text = path.read_text(encoding="utf-8")
        leaks += sum(needle.casefold() in text.casefold() for needle in needles)
    return {
        "file_count": len(files),
        "forbidden_binary_count": forbidden_binary,
        "path_leak_count": leaks,
    }
