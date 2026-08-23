"""Policy-gated tools shared by local agents, HTTP, and MCP transports."""

from __future__ import annotations

import json
import re
import shutil
import threading
from pathlib import Path
from typing import Any, Protocol

from training.company_archive.inspector import CompanyCdrInspector
from training.company_archive.models import CdrInspectionV1
from training.company_archive.safety import (
    assert_source_unchanged,
    resolve_archive_paths,
    resolve_source_file,
    source_stat_guard,
)
from training.corel_operator.capabilities import inspect_operator_capabilities
from training.corel_operator.models import MutationPlanV1
from training.corel_operator.planner import validate_planner_output
from training.corel_operator.policy import source_token
from training.corel_operator.service import SafeCorelOperator
from training.corel_operator.visual_qa import compare_operator_previews


_FILE_ID_RE = re.compile(r"^file:[a-f0-9]{32}$")
_TASK_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$")


class InventoryReader(Protocol):
    def get_file(self, file_id: str) -> dict[str, Any]: ...


class OperatorToolError(ValueError):
    pass


class OperatorToolService:
    """Resolve opaque inventory IDs and serialize all Corel access."""

    def __init__(
        self,
        *,
        archive_root: Path,
        workspace: Path,
        inventory: InventoryReader,
        inspector: CompanyCdrInspector | None = None,
        operator: SafeCorelOperator | None = None,
    ) -> None:
        self.archive_root, self.workspace = resolve_archive_paths(archive_root, workspace)
        self.inventory = inventory
        self.inspector = inspector or CompanyCdrInspector()
        self.operator = operator or SafeCorelOperator()
        self._corel_lock = threading.RLock()

    def _record(self, file_id: str) -> dict[str, Any]:
        if not _FILE_ID_RE.fullmatch(file_id):
            raise OperatorToolError("invalid inventory file ID")
        try:
            row = self.inventory.get_file(file_id)
        except KeyError as exc:
            raise OperatorToolError("inventory file ID was not found") from exc
        if not bool(row.get("cdr_candidate")):
            raise OperatorToolError("inventory file is not a CDR/CDT candidate")
        return row

    def _source(self, file_id: str) -> Path:
        row = self._record(file_id)
        return resolve_source_file(
            Path(str(row["absolute_path"])),
            self.archive_root,
            suffixes={".cdr", ".cdt"},
        )

    def inspect_model(self, file_id: str) -> CdrInspectionV1:
        source = self._source(file_id)
        with self._corel_lock:
            inspection = self.inspector.inspect(source, archive_root=self.archive_root)
        return inspection.model_copy(
            update={"source_path": source_token(source, self.archive_root)}
        )

    def get_document(self, file_id: str) -> dict[str, Any]:
        inspection = self.inspect_model(file_id)
        return {
            "file_id": file_id,
            "source_token": inspection.source_path,
            "corel_version": inspection.corel_version,
            "page_count": inspection.page_count,
            "page_width": inspection.page_width,
            "page_height": inspection.page_height,
            "object_count": inspection.object_count,
            "text_object_count": inspection.text_object_count,
            "bitmap_count": inspection.bitmap_count,
            "vector_count": inspection.vector_count,
            "group_count": inspection.group_count,
            "capabilities": inspect_operator_capabilities(inspection).model_dump(mode="json"),
        }

    def build_agent_context(
        self,
        file_id: str,
        *,
        include_text: bool = False,
        max_text_candidates: int = 25,
    ) -> dict[str, Any]:
        """Build a bounded planner context; customer text is opt-in."""

        # Lazy import keeps the established corel_operator package exports
        # independent from the optional agent layer built above them.
        from training.corel_agent.context import build_document_context

        inspection = self.inspect_model(file_id)
        return build_document_context(
            inspection,
            document_id=file_id,
            include_text=include_text,
            max_text_candidates=max_text_candidates,
        ).model_dump(mode="json")

    def list_objects(
        self,
        file_id: str,
        *,
        object_type: str | None = None,
        include_text: bool = False,
    ) -> dict[str, Any]:
        inspection = self.inspect_model(file_id)
        objects = [
            item
            for item in inspection.objects
            if object_type is None or item.object_type == object_type
        ]
        payload: list[dict[str, Any]] = []
        for item in objects:
            value = item.model_dump(mode="json")
            if not include_text:
                value["text"] = None
            payload.append(value)
        return {"file_id": file_id, "count": len(payload), "objects": payload}

    def find_text(
        self,
        file_id: str,
        *,
        query: str,
        case_sensitive: bool = True,
        regex: bool = False,
    ) -> dict[str, Any]:
        if not query or len(query) > 200:
            raise OperatorToolError("text query must contain 1..200 characters")
        inspection = self.inspect_model(file_id)
        flags = 0 if case_sensitive else re.IGNORECASE
        try:
            pattern = re.compile(query if regex else re.escape(query), flags=flags)
        except re.error as exc:
            raise OperatorToolError(f"invalid text regex: {exc}") from exc
        matches = [
            {
                "object_id": item.object_id,
                "object_type": item.object_type,
                "page": int(item.metadata.get("source_page", 1)),
                "bbox": item.bbox,
                "text": item.text,
            }
            for item in inspection.objects
            if item.text is not None and pattern.search(item.text)
        ]
        return {"file_id": file_id, "match_count": len(matches), "matches": matches}

    def execute_plan(
        self,
        file_id: str,
        *,
        task_id: str,
        plan: MutationPlanV1 | dict[str, Any],
    ) -> dict[str, Any]:
        if not _TASK_ID_RE.fullmatch(task_id):
            raise OperatorToolError("invalid task ID")
        validated = plan if isinstance(plan, MutationPlanV1) else validate_planner_output(plan)
        source = self._source(file_id)
        task_root = (self.workspace / "runs" / task_id).resolve(strict=False)
        try:
            task_root.relative_to(self.workspace)
        except ValueError as exc:
            raise OperatorToolError("task workspace escaped approved root") from exc
        target = task_root / "working_copy.cdr"
        if target.exists():
            raise OperatorToolError("task output already exists; choose a new task ID")
        with self._corel_lock:
            result = self.operator.execute(
                source_path=source,
                archive_root=self.archive_root,
                workspace=self.workspace,
                working_copy_path=target,
                plan=validated,
            )
        payload = result.model_dump(mode="json")
        for key in ("working_copy", "preview_before", "preview_after", "pdf_after"):
            value = payload.get(key)
            if value:
                path = Path(str(value)).resolve(strict=False)
                try:
                    payload[key] = path.relative_to(self.workspace).as_posix()
                except ValueError as exc:
                    raise OperatorToolError("operator returned a path outside workspace") from exc
        payload["file_id"] = file_id
        payload["task_id"] = task_id
        return payload

    def export_copy(
        self,
        file_id: str,
        *,
        task_id: str,
        formats: list[str],
    ) -> dict[str, Any]:
        """Create an editable CDR copy and derivatives without mutating document content."""

        if not _TASK_ID_RE.fullmatch(task_id):
            raise OperatorToolError("invalid task ID")
        requested = {value.upper() for value in formats}
        if not requested or requested - {"CDR", "PDF", "PNG"}:
            raise OperatorToolError("export formats must be CDR, PDF, and/or PNG")
        source = self._source(file_id)
        source_before = source_stat_guard(source)
        task_root = (self.workspace / "runs" / task_id).resolve(strict=False)
        task_root.relative_to(self.workspace)
        target = task_root / "working_copy.cdr"
        if target.exists():
            raise OperatorToolError("task output already exists; choose a new task ID")
        task_root.mkdir(parents=True, exist_ok=False)
        runtime = self.operator.runtime
        document_open = False
        before = None
        reopened = None
        try:
            with self._corel_lock:
                runtime.create_working_copy(source, target)
                runtime.open(target)
                document_open = True
                before = runtime.snapshot(target)
                before_preview = task_root / "working_copy_before.png"
                runtime.export_canonical_png(
                    before_preview,
                    dpi=200,
                    max_dimension=2400,
                    max_pixels=8_000_000,
                )
                shutil.copy2(before_preview, task_root / "working_copy_after.png")
                if "PDF" in requested:
                    runtime.export_pdf(task_root / "working_copy.pdf")
                runtime.close()
                document_open = False
                runtime.open(target)
                document_open = True
                reopened = runtime.snapshot(target)
                runtime.close()
                document_open = False
        finally:
            if document_open:
                try:
                    runtime.close()
                except Exception:
                    pass
            assert_source_unchanged(source, source_before)
        if before is None or reopened is None:
            raise OperatorToolError("export-only editable reopen verification did not complete")
        editability_verified = (
            reopened.object_count == before.object_count
            and {item.object_id for item in reopened.objects}
            == {item.object_id for item in before.objects}
        )
        if not editability_verified:
            raise OperatorToolError("export-only working copy failed editable reopen verification")
        return {
            "result": "AUTO_SUCCESS",
            "file_id": file_id,
            "task_id": task_id,
            "operation_count": 0,
            "working_copy": target.relative_to(self.workspace).as_posix(),
            "preview_before": (task_root / "working_copy_before.png")
            .relative_to(self.workspace)
            .as_posix(),
            "preview_after": (task_root / "working_copy_after.png")
            .relative_to(self.workspace)
            .as_posix(),
            "pdf_after": (
                (task_root / "working_copy.pdf").relative_to(self.workspace).as_posix()
                if (task_root / "working_copy.pdf").is_file()
                else None
            ),
            "source_unchanged": True,
            "transaction_committed": False,
            "rollback_verified": False,
            "editability_verified": True,
            "metadata": {
                "save_completed": True,
                "reopen_completed": True,
                "export_only": True,
                "requested_formats": sorted(requested),
                "visual_qa_v2": {
                    "status": "PASS",
                    "reasons": ["EXPORT_ONLY_NO_MUTATION"],
                },
            },
        }

    def visual_qa(self, *, task_id: str) -> dict[str, Any]:
        if not _TASK_ID_RE.fullmatch(task_id):
            raise OperatorToolError("invalid task ID")
        task_root = (self.workspace / "runs" / task_id).resolve(strict=False)
        v2_report = task_root / "visual_qa_v2.json"
        if v2_report.is_file():
            payload = json.loads(v2_report.read_text(encoding="utf-8"))
            return {"task_id": task_id, **payload}
        before = task_root / "working_copy_before.png"
        after = task_root / "working_copy_after.png"
        report = compare_operator_previews(
            before,
            after,
            workspace=self.workspace,
        )
        return {"task_id": task_id, **report.model_dump(mode="json")}


__all__ = ["InventoryReader", "OperatorToolError", "OperatorToolService"]
