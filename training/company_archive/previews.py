"""Bounded preview batches; never render the full archive implicitly."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from PIL import Image

from training.company_archive.database import ArchiveDatabase
from training.company_archive.inspector import CompanyCdrInspector
from training.company_archive.models import WorkStatus


class PreviewBatcher:
    def __init__(
        self,
        database: ArchiveDatabase,
        workspace: Path,
        *,
        inspector: CompanyCdrInspector | None = None,
    ) -> None:
        self.database = database
        self.workspace = workspace.resolve()
        self.preview_root = self.workspace / "previews"
        self.inspector = inspector or CompanyCdrInspector()

    def render(
        self,
        *,
        archive_root: Path,
        file_ids: Iterable[str] = (),
        limit: int | None = None,
        dpi: int = 96,
    ) -> list[dict]:
        requested = list(dict.fromkeys(file_ids))
        if not requested and limit is None:
            raise ValueError("preview batching requires explicit file IDs or a bounded limit")
        if limit is not None and not 1 <= limit <= 500:
            raise ValueError("preview limit must be between 1 and 500")
        if requested:
            rows = [self.database.get_file(file_id) for file_id in requested]
        else:
            rows = self.database.rows(
                "cdr_candidate=1 AND preview_status!=?", (WorkStatus.COMPLETE.value,)
            )[:limit]

        results: list[dict] = []
        for row in rows[:limit] if limit is not None else rows:
            file_id = str(row["file_id"])
            target = self.preview_root / f"{file_id.removeprefix('file:')}.png"
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists():
                    raise FileExistsError(f"preview already exists: {target}")
                rendered = self.inspector.render_preview(
                    Path(row["absolute_path"]), target, archive_root=archive_root, dpi=dpi
                )
                with Image.open(rendered) as image:
                    width, height = image.size
                self.database.update_fields(
                    file_id,
                    preview_status=WorkStatus.COMPLETE,
                    preview_path=str(rendered),
                    preview_width=width,
                    preview_height=height,
                    render_error=None,
                )
                results.append({"file_id": file_id, "status": "COMPLETE", "path": str(rendered)})
            except Exception as exc:
                self.database.update_fields(
                    file_id,
                    preview_status=WorkStatus.FAILED,
                    render_error=str(exc),
                )
                results.append({"file_id": file_id, "status": "FAILED", "error": str(exc)})
        return results
