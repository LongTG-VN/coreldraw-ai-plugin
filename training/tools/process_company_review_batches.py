"""Render and privately publish resumable company CDR review batches.

This tool is deliberately mechanical: it never scores aesthetics, assigns Gold,
or writes to source CDR files. Source documents are opened by
``CompanyCdrInspector`` and closed without save.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import shutil
import sqlite3
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from PIL import Image, ImageDraw, ImageFont, ImageOps

from corel_bridge import corel_bridge
from training.company_archive.database import ArchiveDatabase
from training.company_archive.inspector import CompanyCdrInspector
from training.company_archive.models import WorkStatus
from training.company_archive.safety import source_stat_guard


STATE_SCHEMA_VERSION = "1.0"
REVIEW_REPOSITORY = "LongTG-VN/coreldraw-ai-review-private"
FORBIDDEN_TEXT = ("C:\\", "Users\\Admin", "Downloads\\", "training\\workspace")
MAX_DIMENSION = 2400
MAX_PIXELS = 8_000_000


class AutonomousReviewError(RuntimeError):
    """Raised when a fail-closed review processing gate is violated."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def run_command(command: list[str], *, cwd: Path) -> str:
    result = subprocess.run(
        command,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode:
        message = (result.stderr or result.stdout).strip()
        raise AutonomousReviewError(f"command failed ({result.returncode}): {message}")
    return result.stdout.strip()


def open_inventory(database_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    return connection


def load_cdr_rows(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in connection.execute(
            "SELECT * FROM files WHERE cdr_candidate=1 ORDER BY relative_path"
        )
    ]


def load_batch_one_mapping(
    connection: sqlite3.Connection, manifest_path: Path
) -> dict[str, str]:
    if not manifest_path.is_file():
        raise AutonomousReviewError(f"batch_001 manifest is missing: {manifest_path}")
    path_to_id = {
        str(Path(row["absolute_path"]).resolve()).casefold(): str(row["file_id"])
        for row in connection.execute("SELECT file_id,absolute_path FROM files")
    }
    mapping: dict[str, str] = {}
    with manifest_path.open("r", encoding="utf-8-sig", newline="") as handle:
        for item in csv.DictReader(handle):
            source_key = str(Path(item["source_path"]).resolve()).casefold()
            file_id = path_to_id.get(source_key)
            if not file_id:
                raise AutonomousReviewError(
                    f"batch_001 source is absent from inventory: {item['design_id']}"
                )
            mapping[file_id] = item["design_id"]
    if len(mapping) != 100:
        raise AutonomousReviewError(
            f"batch_001 must map exactly 100 inventory records, found {len(mapping)}"
        )
    return mapping


def initial_state(
    rows: list[dict[str, Any]], batch_one_mapping: dict[str, str]
) -> dict[str, Any]:
    records: dict[str, dict[str, Any]] = {}
    used_design_ids = set(batch_one_mapping.values())
    next_number = 101
    for row in rows:
        file_id = str(row["file_id"])
        design_id = batch_one_mapping.get(file_id)
        if design_id is None:
            while f"CDR_{next_number:06d}" in used_design_ids:
                next_number += 1
            design_id = f"CDR_{next_number:06d}"
            next_number += 1
        used_design_ids.add(design_id)
        published = file_id in batch_one_mapping
        records[file_id] = {
            "design_id": design_id,
            "status": "REVIEW_PUBLISHED" if published else "UNPROCESSED",
            "batch": "batch_001" if published else None,
            "attempts": 0,
            "error": None,
            "source_guard": None,
        }
    return {
        "schema_version": STATE_SCHEMA_VERSION,
        "started_at": utc_now(),
        "updated_at": utc_now(),
        "current_batch": 2,
        "records": records,
        "runtime_recovery_used": False,
        "source_mutations_detected": 0,
    }


def load_or_create_state(
    state_path: Path,
    rows: list[dict[str, Any]],
    batch_one_mapping: dict[str, str],
) -> dict[str, Any]:
    if state_path.is_file():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        if state.get("schema_version") != STATE_SCHEMA_VERSION:
            raise AutonomousReviewError("unsupported autonomous review state schema")
        if set(state.get("records", {})) != {str(row["file_id"]) for row in rows}:
            raise AutonomousReviewError("inventory membership changed after ID assignment")
        for file_id, design_id in batch_one_mapping.items():
            record = state["records"][file_id]
            if record["design_id"] != design_id:
                raise AutonomousReviewError("batch_001 stable design ID mapping changed")
        return state
    state = initial_state(rows, batch_one_mapping)
    atomic_json(state_path, state)
    return state


def canonical_file_ids(rows: list[dict[str, Any]]) -> set[str]:
    groups: dict[str, list[dict[str, Any]]] = {}
    canonical: set[str] = set()
    for row in rows:
        group = row.get("duplicate_group_id")
        if group:
            groups.setdefault(str(group), []).append(row)
        else:
            canonical.add(str(row["file_id"]))
    for members in groups.values():
        members.sort(key=lambda item: str(item["relative_path"]).casefold())
        canonical.add(str(members[0]["file_id"]))
    return canonical


def save_progress(
    progress_path: Path,
    state_path: Path,
    state: dict[str, Any],
    *,
    total_cdr: int,
) -> None:
    statuses = [item["status"] for item in state["records"].values()]
    processed = sum(status != "UNPROCESSED" for status in statuses)
    published = statuses.count("REVIEW_PUBLISHED")
    success = published + statuses.count("PREVIEW_SUCCESS")
    failed = statuses.count("PREVIEW_FAILED")
    skipped = statuses.count("SKIPPED_WITH_REASON")
    remaining = statuses.count("UNPROCESSED")
    last_design_id = max(
        (
            item["design_id"]
            for item in state["records"].values()
            if item["status"] != "UNPROCESSED"
        ),
        default=None,
    )
    state["updated_at"] = utc_now()
    atomic_json(state_path, state)
    atomic_json(
        progress_path,
        {
            "schema_version": STATE_SCHEMA_VERSION,
            "total_cdr": total_cdr,
            "processed": processed,
            "preview_success": success,
            "preview_failed": failed,
            "skipped": skipped,
            "review_published": published,
            "remaining": remaining,
            "current_batch": f"batch_{int(state['current_batch']):03d}",
            "last_design_id": last_design_id,
            "started_at": state["started_at"],
            "updated_at": state["updated_at"],
            "failure_count": failed,
            "source_mutations_detected": state["source_mutations_detected"],
        },
    )


def source_matches_inventory(row: dict[str, Any]) -> bool:
    source = Path(row["absolute_path"])
    if not source.is_file():
        return False
    stat = source.stat()
    return stat.st_size == int(row["size_bytes"]) and abs(
        stat.st_mtime - float(row["modified_time"])
    ) <= 1e-6


def verify_preview(path: Path) -> tuple[int, int]:
    with Image.open(path) as image:
        width, height = image.size
        image.verify()
    if width < 1 or height < 1:
        raise AutonomousReviewError("preview has invalid dimensions")
    if width > MAX_DIMENSION or height > MAX_DIMENSION or width * height > MAX_PIXELS:
        raise AutonomousReviewError("RENDER_PIXEL_BUDGET_EXCEEDED")
    return width, height


def archive_failed_artifact(target: Path, *, attempt: int) -> None:
    if not target.exists():
        return
    failed_root = target.parent.parent / "failed_artifacts"
    failed_root.mkdir(parents=True, exist_ok=True)
    destination = failed_root / f"{target.stem}.attempt_{attempt}{target.suffix}"
    if destination.exists():
        destination = failed_root / (
            f"{target.stem}.attempt_{attempt}.{int(time.time())}{target.suffix}"
        )
    target.replace(destination)


def concise_error(exc: BaseException, *, limit: int = 600) -> str:
    message = " ".join(str(exc).split()) or exc.__class__.__name__
    return message[:limit]


def ensure_corel_runtime() -> None:
    info = corel_bridge.connection_info()
    if not info.get("connected"):
        raise AutonomousReviewError(f"COREL_RUNTIME_BLOCKED: {info.get('error', 'unknown')}")


def render_one(
    inspector: CompanyCdrInspector,
    row: dict[str, Any],
    record: dict[str, Any],
    *,
    archive_root: Path,
    target: Path,
) -> tuple[bool, str | None]:
    source = Path(row["absolute_path"])
    if not source_matches_inventory(row):
        return False, "SOURCE_METADATA_CHANGED_SINCE_INVENTORY"
    before = source_stat_guard(source)
    record["source_guard"] = list(before)
    for attempt in range(1, 3):
        record["attempts"] = int(record.get("attempts", 0)) + 1
        archive_failed_artifact(target, attempt=attempt)
        try:
            inspector.render_preview(
                source,
                target,
                archive_root=archive_root,
                dpi=96,
                max_dimension=MAX_DIMENSION,
                max_pixels=MAX_PIXELS,
            )
            verify_preview(target)
            if source_stat_guard(source) != before:
                raise AutonomousReviewError("SOURCE_MUTATION_DETECTED")
            return True, None
        except Exception as exc:
            if source_stat_guard(source) != before:
                raise AutonomousReviewError("SOURCE_MUTATION_DETECTED") from exc
            error = concise_error(exc)
            archive_failed_artifact(target, attempt=attempt)
            if "could not close source CDR" in error or "SOURCE_MUTATION" in error:
                raise AutonomousReviewError(error) from exc
            if attempt == 2:
                ensure_corel_runtime()
                return False, error
            time.sleep(0.5)
            ensure_corel_runtime()
    raise AssertionError("unreachable")


def load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for candidate in (
        Path("C:/Windows/Fonts/arialbd.ttf"),
        Path("C:/Windows/Fonts/arial.ttf"),
    ):
        if candidate.is_file():
            return ImageFont.truetype(str(candidate), size=size)
    return ImageFont.load_default()


def write_contact_sheets(
    batch_root: Path, manifest_rows: list[dict[str, Any]], batch_number: int
) -> list[Path]:
    columns = 5
    rows_per_sheet = 5
    cell_width = 520
    cell_height = 390
    header_height = 64
    image_box = (480, 320)
    label_font = load_font(25)
    header_font = load_font(30)
    sheet_count = math.ceil(len(manifest_rows) / 25)
    sheets: list[Path] = []
    for sheet_index in range(sheet_count):
        sheet_rows = manifest_rows[sheet_index * 25 : (sheet_index + 1) * 25]
        visible_rows = math.ceil(len(sheet_rows) / columns)
        sheet = Image.new(
            "RGB",
            (columns * cell_width, header_height + visible_rows * cell_height),
            "#E5E7EB",
        )
        draw = ImageDraw.Draw(sheet)
        draw.text(
            (24, 16),
            f"Company CDR Review Batch {batch_number:03d} — Sheet {sheet_index + 1}/{sheet_count}",
            font=header_font,
            fill="#111827",
        )
        for index, item in enumerate(sheet_rows):
            column = index % columns
            row_index = index // columns
            x0 = column * cell_width
            y0 = header_height + row_index * cell_height
            panel = (x0 + 12, y0 + 10, x0 + cell_width - 12, y0 + cell_height - 10)
            draw.rounded_rectangle(panel, radius=10, fill="#FFFFFF", outline="#CBD5E1", width=2)
            with Image.open(item["preview_path"]) as source_image:
                preview = ImageOps.exif_transpose(source_image).convert("RGB")
                preview.thumbnail(image_box, Image.Resampling.LANCZOS)
                image_x = x0 + (cell_width - preview.width) // 2
                image_y = y0 + 18 + (image_box[1] - preview.height) // 2
                sheet.paste(preview, (image_x, image_y))
            label = item["design_id"]
            label_box = draw.textbbox((0, 0), label, font=label_font)
            label_width = label_box[2] - label_box[0]
            draw.text(
                (x0 + (cell_width - label_width) // 2, y0 + 346),
                label,
                font=label_font,
                fill="#111827",
            )
        sheet_path = batch_root / f"contact_sheet_{sheet_index + 1:03d}.jpg"
        sheet.save(sheet_path, format="JPEG", quality=94, subsampling=0, optimize=True)
        sheets.append(sheet_path)
    return sheets


def write_local_batch(
    batch_root: Path,
    batch_number: int,
    file_ids: list[str],
    state: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[Path]]:
    manifest_rows: list[dict[str, Any]] = []
    for position, file_id in enumerate(file_ids, start=1):
        record = state["records"][file_id]
        preview = batch_root / "previews" / f"{record['design_id']}.png"
        verify_preview(preview)
        manifest_rows.append(
            {
                "design_id": record["design_id"],
                "file_id": file_id,
                "preview_path": str(preview),
                "contact_sheet": f"contact_sheet_{math.ceil(position / 25):03d}.jpg",
                "sheet_position": ((position - 1) % 25) + 1,
                "source_token": record["design_id"],
                "render_status": "PREVIEW_SUCCESS",
            }
        )
    sheets = write_contact_sheets(batch_root, manifest_rows, batch_number)
    with (batch_root / "manifest.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "design_id",
                "file_id",
                "preview_path",
                "contact_sheet",
                "sheet_position",
                "source_token",
                "render_status",
            ],
        )
        writer.writeheader()
        writer.writerows(manifest_rows)
    summary = {
        "schema_version": STATE_SCHEMA_VERSION,
        "review_batch": f"batch_{batch_number:03d}",
        "status": "AESTHETIC_REVIEW_PENDING",
        "design_count": len(manifest_rows),
        "contact_sheet_count": len(sheets),
        "source_cdr_included": False,
        "gold_certification": "NONE",
        "render_bounds": {
            "max_dimension": MAX_DIMENSION,
            "max_pixels": MAX_PIXELS,
        },
    }
    atomic_json(batch_root / "review_batch_summary.json", summary)
    return manifest_rows, sheets


def write_private_batch_files(
    private_batch: Path,
    *,
    batch_number: int,
    manifest_rows: list[dict[str, Any]],
    sheets: list[Path],
) -> None:
    if private_batch.exists():
        raise AutonomousReviewError(f"private batch path already exists: {private_batch}")
    contact_root = private_batch / "contact_sheets"
    contact_root.mkdir(parents=True)
    for sheet in sheets:
        shutil.copy2(sheet, contact_root / sheet.name)
    with (private_batch / "manifest_review.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "design_id",
                "contact_sheet",
                "sheet_position",
                "source_token",
                "render_status",
            ],
        )
        writer.writeheader()
        for item in manifest_rows:
            writer.writerow(
                {
                    "design_id": item["design_id"],
                    "contact_sheet": f"contact_sheets/{item['contact_sheet']}",
                    "sheet_position": item["sheet_position"],
                    "source_token": item["source_token"],
                    "render_status": "PREVIEW_SUCCESS",
                }
            )
    (private_batch / "README.md").write_text(
        f"""# Company CDR Review Batch {batch_number:03d}

Status: AESTHETIC_REVIEW_PENDING

Design count: {len(manifest_rows)}

Contact sheets: {len(sheets)}

Source CDR: NOT INCLUDED

Gold certification: NONE

Review authority: ChatGPT aesthetic triage + human final approval

Allowed first-pass decisions:

- STRONG_GOLD_CANDIDATE
- KEEP
- MAYBE
- REJECT
""",
        encoding="utf-8",
    )
    atomic_json(
        private_batch / "review_batch_summary.json",
        {
            "schema_version": STATE_SCHEMA_VERSION,
            "batch_id": f"batch_{batch_number:03d}",
            "status": "AESTHETIC_REVIEW_PENDING",
            "design_count": len(manifest_rows),
            "contact_sheet_count": len(sheets),
            "source_files_included": False,
            "gold_certification": "NONE",
            "manifest": "manifest_review.csv",
        },
    )


def verify_private_visibility(gh: Path, private_repo: Path) -> None:
    payload = json.loads(
        run_command(
            [
                str(gh),
                "repo",
                "view",
                REVIEW_REPOSITORY,
                "--json",
                "nameWithOwner,visibility,isPrivate",
            ],
            cwd=private_repo,
        )
    )
    if payload.get("nameWithOwner") != REVIEW_REPOSITORY or not payload.get("isPrivate"):
        raise AutonomousReviewError("BLOCKED_DESTINATION_NOT_PRIVATE")
    if str(payload.get("visibility", "")).upper() != "PRIVATE":
        raise AutonomousReviewError("BLOCKED_DESTINATION_NOT_PRIVATE")


def audit_private_batch(private_batch: Path, expected_rows: int) -> None:
    files = [path for path in private_batch.rglob("*") if path.is_file()]
    if any(path.suffix.casefold() in {".cdr", ".cdt"} for path in files):
        raise AutonomousReviewError("source CDR found in private batch")
    if any(path.name.casefold() == "archive.sqlite" for path in files):
        raise AutonomousReviewError("archive.sqlite found in private batch")
    if any(path.parent.name == "previews" for path in files):
        raise AutonomousReviewError("full previews must remain local")
    text_files = [path for path in files if path.suffix.casefold() in {".md", ".csv", ".json", ".txt"}]
    for path in text_files:
        content = path.read_text(encoding="utf-8-sig")
        for forbidden in FORBIDDEN_TEXT:
            if forbidden in content:
                raise AutonomousReviewError(f"local path leak in {path.name}: {forbidden}")
    with (private_batch / "manifest_review.csv").open(
        "r", encoding="utf-8-sig", newline=""
    ) as handle:
        if len(list(csv.DictReader(handle))) != expected_rows:
            raise AutonomousReviewError("private manifest row count mismatch")
    total_bytes = sum(path.stat().st_size for path in files)
    if total_bytes > 100 * 1024 * 1024:
        raise AutonomousReviewError("private batch exceeds 100 MB")


def publish_batch(
    private_repo: Path,
    gh: Path,
    *,
    batch_number: int,
    manifest_rows: list[dict[str, Any]],
    sheets: list[Path],
) -> str:
    verify_private_visibility(gh, private_repo)
    private_batch = private_repo / "company_archive" / f"batch_{batch_number:03d}"
    relative = f"company_archive/batch_{batch_number:03d}"
    status = run_command(["git", "status", "--porcelain"], cwd=private_repo)
    if status:
        changed = [line[3:].replace("\\", "/") for line in status.splitlines()]
        if any(not path.startswith(relative + "/") for path in changed):
            raise AutonomousReviewError("private review repository has unrelated changes")
    if not private_batch.exists():
        write_private_batch_files(
            private_batch,
            batch_number=batch_number,
            manifest_rows=manifest_rows,
            sheets=sheets,
        )
    audit_private_batch(private_batch, len(manifest_rows))
    run_command(["git", "add", "--", relative], cwd=private_repo)
    run_command(["git", "diff", "--cached", "--check"], cwd=private_repo)
    staged = run_command(["git", "diff", "--cached", "--name-only"], cwd=private_repo)
    commit = ""
    if staged:
        commit = run_command(
            [
                "git",
                "commit",
                "-m",
                f"data(review): publish company CDR review batch {batch_number:03d}",
            ],
            cwd=private_repo,
        )
    run_command(["git", "push", "origin", "main"], cwd=private_repo)
    local_head = run_command(["git", "rev-parse", "HEAD"], cwd=private_repo)
    run_command(["git", "fetch", "origin"], cwd=private_repo)
    remote_head = run_command(["git", "rev-parse", "origin/main"], cwd=private_repo)
    if local_head != remote_head:
        raise AutonomousReviewError("private repository local/remote HEAD mismatch")
    verify_private_visibility(gh, private_repo)
    remote_tree = json.loads(
        run_command(
            [
                str(gh),
                "api",
                f"repos/{REVIEW_REPOSITORY}/git/trees/main?recursive=1",
            ],
            cwd=private_repo,
        )
    )
    paths = {item["path"] for item in remote_tree.get("tree", []) if item.get("type") == "blob"}
    prefix = relative + "/"
    remote_batch = {path for path in paths if path.startswith(prefix)}
    remote_sheets = {path for path in remote_batch if "/contact_sheets/contact_sheet_" in path}
    if len(remote_sheets) != len(sheets):
        raise AutonomousReviewError("remote contact sheet count mismatch")
    if f"{relative}/manifest_review.csv" not in remote_batch:
        raise AutonomousReviewError("remote sanitized manifest is missing")
    if any(path.casefold().endswith((".cdr", ".cdt")) for path in remote_batch):
        raise AutonomousReviewError("remote batch contains source CDR")
    print(commit, flush=True)
    return local_head


def batch_success_ids(state: dict[str, Any], batch_number: int) -> list[str]:
    batch_name = f"batch_{batch_number:03d}"
    return sorted(
        (
            file_id
            for file_id, item in state["records"].items()
            if item["batch"] == batch_name and item["status"] == "PREVIEW_SUCCESS"
        ),
        key=lambda file_id: state["records"][file_id]["design_id"],
    )


def reset_missing_batch_previews(
    state: dict[str, Any], workspace: Path, batch_number: int
) -> None:
    batch_name = f"batch_{batch_number:03d}"
    for record in state["records"].values():
        if record["batch"] != batch_name or record["status"] != "PREVIEW_SUCCESS":
            continue
        preview = workspace / f"review_batch_{batch_number:03d}" / "previews" / (
            record["design_id"] + ".png"
        )
        try:
            verify_preview(preview)
        except Exception:
            record["status"] = "UNPROCESSED"
            record["batch"] = None
            record["error"] = "RESUME_PREVIEW_MISSING_OR_INVALID"


def mark_noncanonical_skips(
    rows: list[dict[str, Any]],
    state: dict[str, Any],
    canonical: set[str],
    database: ArchiveDatabase,
) -> None:
    for row in rows:
        file_id = str(row["file_id"])
        record = state["records"][file_id]
        if file_id not in canonical and record["status"] == "UNPROCESSED":
            record["status"] = "SKIPPED_WITH_REASON"
            record["error"] = "SHA256_VERIFIED_DUPLICATE_NONCANONICAL"
            database.update_fields(
                file_id,
                preview_status=WorkStatus.NOT_APPLICABLE,
                notes="SKIPPED: SHA256_VERIFIED_DUPLICATE_NONCANONICAL",
            )


def verify_batch_source_guards(
    rows_by_id: dict[str, dict[str, Any]],
    state: dict[str, Any],
    file_ids: Iterable[str],
) -> None:
    for file_id in file_ids:
        saved = state["records"][file_id].get("source_guard")
        if saved is None:
            continue
        source = Path(rows_by_id[file_id]["absolute_path"])
        if tuple(saved) != source_stat_guard(source):
            state["source_mutations_detected"] += 1
            raise AutonomousReviewError("SOURCE_SAFETY_BLOCKED")


def write_final_report(
    report_path: Path,
    state: dict[str, Any],
    *,
    total_cdr: int,
    private_repo: Path,
    public_repo: Path,
) -> dict[str, Any]:
    statuses = [item["status"] for item in state["records"].values()]
    batches = sorted(
        {
            item["batch"]
            for item in state["records"].values()
            if item.get("batch") and item["status"] == "REVIEW_PUBLISHED"
        }
    )
    contact_sheets = sum(
        len(list((private_repo / "company_archive" / batch / "contact_sheets").glob("*.jpg")))
        for batch in batches
    )
    tracked_workspace = run_command(
        ["git", "ls-files", "training/workspace/company_archive"], cwd=public_repo
    )
    report = {
        "STATUS": (
            "ALL_CDR_REVIEW_BATCHES_READY"
            if statuses.count("UNPROCESSED") == 0
            and state["source_mutations_detected"] == 0
            else "AUTONOMOUS_REVIEW_BLOCKED"
        ),
        "TOTAL_CDR": total_cdr,
        "TOTAL_RENDERED": statuses.count("REVIEW_PUBLISHED") + statuses.count("PREVIEW_SUCCESS"),
        "TOTAL_FAILED": statuses.count("PREVIEW_FAILED"),
        "TOTAL_SKIPPED": statuses.count("SKIPPED_WITH_REASON"),
        "TOTAL_BATCHES": len(batches),
        "LAST_BATCH": batches[-1] if batches else None,
        "CONTACT_SHEETS": contact_sheets,
        "SOURCE_MUTATIONS": state["source_mutations_detected"],
        "PRIVATE_REPOSITORY": REVIEW_REPOSITORY,
        "PUBLIC_REPO_CONTAMINATION": 1 if tracked_workspace else 0,
        "UNPROCESSED_REMAINING": statuses.count("UNPROCESSED"),
        "completed_at": utc_now(),
    }
    atomic_json(report_path, report)
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive-root", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--private-repo", type=Path, required=True)
    parser.add_argument("--gh", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=100)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if not 1 <= args.batch_size <= 100:
        raise SystemExit("--batch-size must be between 1 and 100")
    archive_root = args.archive_root.expanduser().resolve(strict=True)
    workspace = args.workspace.expanduser().resolve(strict=True)
    private_repo = args.private_repo.expanduser().resolve(strict=True)
    public_repo = Path(__file__).resolve().parents[2]
    gh = args.gh.expanduser().resolve(strict=True)
    if archive_root == workspace or archive_root in workspace.parents or workspace in archive_root.parents:
        raise AutonomousReviewError("archive root and workspace must be disjoint")
    database_path = workspace / "archive.sqlite"
    state_path = workspace / "AUTONOMOUS_REVIEW_STATE.json"
    progress_path = workspace / "AUTONOMOUS_REVIEW_PROGRESS.json"
    final_report_path = workspace / "AUTONOMOUS_REVIEW_FINAL_REPORT.json"
    batch_one_manifest = workspace / "review_batch_001" / "manifest.csv"

    connection = open_inventory(database_path)
    database = ArchiveDatabase(database_path)
    rows = load_cdr_rows(connection)
    rows_by_id = {str(row["file_id"]): row for row in rows}
    batch_one_mapping = load_batch_one_mapping(connection, batch_one_manifest)
    state = load_or_create_state(state_path, rows, batch_one_mapping)
    canonical = canonical_file_ids(rows)
    mark_noncanonical_skips(rows, state, canonical, database)
    save_progress(progress_path, state_path, state, total_cdr=len(rows))
    ensure_corel_runtime()
    verify_private_visibility(gh, private_repo)
    inspector = CompanyCdrInspector()

    try:
        while True:
            batch_number = int(state["current_batch"])
            reset_missing_batch_previews(state, workspace, batch_number)
            unprocessed = [
                row
                for row in rows
                if state["records"][str(row["file_id"])]["status"] == "UNPROCESSED"
            ]
            batch_name = f"batch_{batch_number:03d}"
            batch_root = workspace / f"review_batch_{batch_number:03d}"
            (batch_root / "previews").mkdir(parents=True, exist_ok=True)
            successful = batch_success_ids(state, batch_number)
            touched: list[str] = []
            while len(successful) < args.batch_size and unprocessed:
                row = unprocessed.pop(0)
                file_id = str(row["file_id"])
                record = state["records"][file_id]
                design_id = record["design_id"]
                target = batch_root / "previews" / f"{design_id}.png"
                record["batch"] = batch_name
                touched.append(file_id)
                ok, error = render_one(
                    inspector,
                    row,
                    record,
                    archive_root=archive_root,
                    target=target,
                )
                if ok:
                    record["status"] = "PREVIEW_SUCCESS"
                    record["error"] = None
                    successful.append(file_id)
                    width, height = verify_preview(target)
                    database.update_fields(
                        file_id,
                        preview_status=WorkStatus.COMPLETE,
                        preview_path=str(target.resolve()),
                        preview_width=width,
                        preview_height=height,
                        render_error=None,
                    )
                else:
                    if error == "SOURCE_METADATA_CHANGED_SINCE_INVENTORY":
                        record["status"] = "SKIPPED_WITH_REASON"
                        database.update_fields(
                            file_id,
                            preview_status=WorkStatus.NOT_APPLICABLE,
                            render_error=error,
                            notes="SKIPPED: SOURCE_METADATA_CHANGED_SINCE_INVENTORY",
                        )
                    else:
                        record["status"] = "PREVIEW_FAILED"
                        database.update_fields(
                            file_id,
                            preview_status=WorkStatus.FAILED,
                            render_error=error,
                        )
                    record["error"] = error
                save_progress(progress_path, state_path, state, total_cdr=len(rows))
                print(
                    json.dumps(
                        {
                            "event": "file_processed",
                            "design_id": design_id,
                            "status": record["status"],
                            "batch": batch_name,
                            "batch_success": len(successful),
                            "remaining": sum(
                                item["status"] == "UNPROCESSED"
                                for item in state["records"].values()
                            ),
                        }
                    ),
                    flush=True,
                )
            verify_batch_source_guards(rows_by_id, state, touched)
            save_progress(progress_path, state_path, state, total_cdr=len(rows))
            if successful:
                manifest_rows, sheets = write_local_batch(
                    batch_root, batch_number, successful, state
                )
                publish_batch(
                    private_repo,
                    gh,
                    batch_number=batch_number,
                    manifest_rows=manifest_rows,
                    sheets=sheets,
                )
                for file_id in successful:
                    state["records"][file_id]["status"] = "REVIEW_PUBLISHED"
                state["current_batch"] = batch_number + 1
                save_progress(progress_path, state_path, state, total_cdr=len(rows))
                print(
                    json.dumps(
                        {
                            "event": "batch_published",
                            "batch": batch_name,
                            "design_count": len(successful),
                            "contact_sheets": len(sheets),
                        }
                    ),
                    flush=True,
                )
            if not any(
                item["status"] == "UNPROCESSED" for item in state["records"].values()
            ):
                break
            if not successful:
                raise AutonomousReviewError("no progress while unprocessed records remain")
    except Exception as exc:
        if (
            "SOURCE_MUTATION" in str(exc) or "SOURCE_SAFETY" in str(exc)
        ) and state["source_mutations_detected"] == 0:
            state["source_mutations_detected"] = 1
        save_progress(progress_path, state_path, state, total_cdr=len(rows))
        raise
    finally:
        connection.close()

    verify_batch_source_guards(
        rows_by_id,
        state,
        (
            file_id
            for file_id, item in state["records"].items()
            if item.get("source_guard") is not None
        ),
    )
    report = write_final_report(
        final_report_path,
        state,
        total_cdr=len(rows),
        private_repo=private_repo,
        public_repo=public_repo,
    )
    print(json.dumps(report, indent=2), flush=True)
    return 0 if report["STATUS"] == "ALL_CDR_REVIEW_BATCHES_READY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
