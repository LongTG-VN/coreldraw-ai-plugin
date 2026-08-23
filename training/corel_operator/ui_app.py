"""Local-only UI for supervised Codex-to-Corel working-copy operations."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Literal, Protocol

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from PIL import Image, ImageChops, ImageEnhance
from pydantic import ConfigDict, Field, model_validator

from training.corel_agent.commands import analyze_vietnamese_command
from training.corel_agent.models import CorelAgentRequestV1, CorelPlanEnvelopeV1
from training.corel_agent.policy import validate_agent_plan
from training.corel_agent.provider import PlannerProviderError, validate_untrusted_planner_payload
from training.corel_operator.models import StrictModel
from training.corel_operator.tools import OperatorToolService
from training.corel_operator.ui_state import (
    PathOpener,
    UiJobRecordV1,
    UiJobStore,
    UiOutputManager,
    UiSettingsStore,
    UiSettingsV1,
    open_local_path,
)


_FILE_ID_RE = re.compile(r"^file:[a-f0-9]{32}$")
_TASK_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$")


class UiDocumentRequestV1(StrictModel):
    file_id: str = Field(pattern=_FILE_ID_RE.pattern)


class UiPlanRequestV1(UiDocumentRequestV1):
    instruction: str = Field(min_length=1, max_length=2000)


class UiApprovalRequestV1(StrictModel):
    task_id: str = Field(pattern=_TASK_ID_RE.pattern)
    approved: Literal[True]


class UiCancelRequestV1(StrictModel):
    task_id: str = Field(pattern=_TASK_ID_RE.pattern)


class UiOpenRequestV1(UiCancelRequestV1):
    kind: Literal["folder", "cdr", "pdf", "png"]


class UiLifecycleRequestV1(StrictModel):
    action: Literal["shutdown", "restart"]


class CodexPlanningResultV1(StrictModel):
    status: Literal["PLANNED", "NEEDS_REVIEW", "REJECTED"]
    message: str = Field(min_length=1, max_length=500)
    envelope: CorelPlanEnvelopeV1 | None = None

    @model_validator(mode="after")
    def bind_status_to_envelope(self) -> "CodexPlanningResultV1":
        if (self.status == "PLANNED") != (self.envelope is not None):
            raise ValueError("PLANNED requires one envelope; held plans must not include one")
        return self


class _CodexCliRawResultV1(StrictModel):
    status: Literal["PLANNED", "NEEDS_REVIEW", "REJECTED"]
    message: str = Field(min_length=1, max_length=500)
    envelope: CorelPlanEnvelopeV1 | None


def _codex_output_schema() -> dict[str, Any]:
    """Make Pydantic's schema compatible with strict Responses structured output."""

    schema = _CodexCliRawResultV1.model_json_schema()
    defs = schema["$defs"]
    defs["MutationPlanV1"]["properties"]["metadata"] = {
        "type": "object",
        "additionalProperties": False,
        "properties": {},
        "required": [],
    }
    value_schema = defs["MutationActionV1"]["properties"]["value"]
    value_schema["anyOf"] = [
        {"type": "string"},
        {"type": "number"},
        {
            "type": "object",
            "additionalProperties": False,
            "properties": {"x": {"type": "number"}, "y": {"type": "number"}},
            "required": ["x", "y"],
        },
        {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "width": {"type": "number"},
                "height": {"type": "number"},
            },
            "required": ["width", "height"],
        },
    ]

    def require_every_property(node: Any) -> None:
        if isinstance(node, dict):
            node.pop("default", None)
            if node.get("type") == "object":
                node["additionalProperties"] = False
            properties = node.get("properties")
            if isinstance(properties, dict):
                node["required"] = list(properties)
            for value in node.values():
                require_every_property(value)
        elif isinstance(node, list):
            for value in node:
                require_every_property(value)

    require_every_property(schema)
    return schema


class PlanBroker(Protocol):
    def plan(self, *, file_id: str, task_id: str, instruction: str) -> CodexPlanningResultV1: ...


class CodexPlannerUnavailable(RuntimeError):
    pass


class HealthProbe(Protocol):
    def probe(self) -> dict[str, Any]: ...


class CodexCliPlanBroker:
    """Invoke the authenticated Codex host in read-only, plan-only mode."""

    def __init__(
        self,
        *,
        repo_root: Path,
        workspace: Path,
        executable: str | None = None,
        timeout_seconds: int = 180,
    ) -> None:
        self.repo_root = repo_root.resolve()
        self.workspace = workspace.resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.executable = executable or shutil.which("codex") or ""
        self.timeout_seconds = timeout_seconds

    def _command(self, *, schema_path: Path, output_path: Path) -> list[str]:
        if not self.executable:
            raise CodexPlannerUnavailable("Codex CLI is not available on PATH")
        return [
            self.executable,
            "-a",
            "never",
            "-s",
            "read-only",
            "-C",
            str(self.repo_root),
            "-c",
            "mcp_servers.node_repl.enabled=false",
            "-c",
            "mcp_servers.openaiDeveloperDocs.enabled=false",
            "exec",
            "--ephemeral",
            "--json",
            "--output-schema",
            str(schema_path),
            "-o",
            str(output_path),
            "-",
        ]

    @staticmethod
    def _prompt(*, file_id: str, task_id: str, instruction: str) -> str:
        return f"""Act now on this complete PLAN-ONLY request; do not ask for more input.
Call corel_operator.corel_list_objects for {file_id} with include_text=true. Use it to
verify the stable object ID and type in this exact request:
{json.dumps(instruction, ensure_ascii=False)}

Never call corel_plan_task, corel_run_task, corel_execute_plan, shell, COM, or VBA.
If unresolved/ambiguous/unsafe, return NEEDS_REVIEW or REJECTED with envelope=null.
If safe, return PLANNED with a strict CorelPlanEnvelopeV1 in envelope. It must bind
request_id=plan.plan_id={task_id} and
document_id={file_id}; goal/intent are the exact instruction; plan.source="llm";
expected_object_count_change=0; rollback_on_error=true; constraints include
source_read_only and working_copy_only; confidence is 0..1; requires_review=false.
Use only the bounded actions explicitly required by the request (maximum 10),
with object_id selectors whenever the object is identified
(verified object_type, page=1, require_unique=true, maximum_scope=one_object). For a
text object's direct parent, add a DEPENDENT_CONTAINER dependency allowing only bbox.
Set provenance to schema_version=1.0, planner_type=llm,
planner_provider=codex-host, planner_model=codex, planner_is_ai=true. Request CDR,
PDF, and PNG outputs to job_workspace with overwrite=false. Return JSON now.
"""

    @staticmethod
    def _verify_read_only_mcp_trace(stdout: str) -> None:
        completed_read = False
        forbidden = {"corel_plan_task", "corel_run_task", "corel_execute_plan"}
        for line in stdout.splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            item = event.get("item") if isinstance(event, dict) else None
            if not isinstance(item, dict) or item.get("type") != "mcp_tool_call":
                continue
            if item.get("server") != "corel_operator":
                raise CodexPlannerUnavailable("Codex used an unapproved MCP server")
            tool = str(item.get("tool", ""))
            if tool in forbidden:
                raise CodexPlannerUnavailable("Codex attempted a mutation-capable MCP tool")
            if tool in {"corel_get_document", "corel_build_agent_context", "corel_list_objects", "corel_find_text"} and item.get("status") == "completed":
                completed_read = True
        if not completed_read:
            raise CodexPlannerUnavailable("Codex did not complete a read-only Corel MCP inspection")

    def plan(self, *, file_id: str, task_id: str, instruction: str) -> CodexPlanningResultV1:
        analysis = analyze_vietnamese_command(instruction)
        if analysis.disposition != "EXPLICIT":
            return CodexPlanningResultV1(
                status=("REJECTED" if analysis.disposition == "OUTPUT_ONLY_UNSUPPORTED" else "NEEDS_REVIEW"),
                message=(analysis.reasons[0] if analysis.reasons else analysis.disposition),
            )
        task_root = (self.workspace / "planner" / task_id).resolve(strict=False)
        try:
            task_root.relative_to(self.workspace)
        except ValueError as exc:
            raise CodexPlannerUnavailable("planner task escaped approved workspace") from exc
        task_root.mkdir(parents=True, exist_ok=False)
        schema_path = task_root / "output_schema.json"
        output_path = task_root / "planning_result.json"
        schema_path.write_text(
            json.dumps(_codex_output_schema(), indent=2),
            encoding="utf-8",
        )
        prompt = self._prompt(file_id=file_id, task_id=task_id, instruction=instruction)
        try:
            completed = subprocess.run(
                self._command(schema_path=schema_path, output_path=output_path),
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                input=prompt,
                timeout=self.timeout_seconds,
                check=False,
                shell=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise CodexPlannerUnavailable("Codex plan-only process did not complete") from exc
        if completed.returncode != 0 or not output_path.is_file():
            raise CodexPlannerUnavailable("Codex plan-only process returned no valid result")
        self._verify_read_only_mcp_trace(completed.stdout)
        try:
            raw_result = _CodexCliRawResultV1.model_validate_json(
                output_path.read_text(encoding="utf-8")
            )
        except Exception as exc:
            raise CodexPlannerUnavailable("Codex returned invalid structured planning output") from exc
        envelope = raw_result.envelope
        if envelope is not None:
            try:
                envelope = validate_untrusted_planner_payload(envelope.model_dump(mode="json"))
            except PlannerProviderError as exc:
                raise CodexPlannerUnavailable("Codex plan failed strict schema validation") from exc
            if (
                envelope.request_id != task_id
                or envelope.document_id != file_id
                or envelope.plan.source != "llm"
                or not envelope.provenance.planner_is_ai
            ):
                raise CodexPlannerUnavailable("Codex plan provenance or request binding is invalid")
        try:
            return CodexPlanningResultV1(
                status=raw_result.status,
                message=raw_result.message,
                envelope=envelope,
            )
        except Exception as exc:
            raise CodexPlannerUnavailable("Codex result status and plan are inconsistent") from exc


@dataclass
class _PlanRecord:
    task_id: str
    file_id: str
    instruction: str
    result: CodexPlanningResultV1 | None
    validation: dict[str, Any] | None
    kind: Literal["MUTATION", "EXPORT_ONLY"] = "MUTATION"
    export_formats: list[str] | None = None
    canceled: bool = False
    executing: bool = False
    execution: dict[str, Any] | None = None
    output_version: int | None = None
    outputs: dict[str, str] | None = None


def _plan_summary(record: _PlanRecord) -> dict[str, Any]:
    if record.kind == "EXPORT_ONLY":
        can_approve = not record.canceled and not record.executing and record.execution is None
        return {
            "task_id": record.task_id,
            "file_id": record.file_id,
            "kind": record.kind,
            "status": "PLANNED",
            "message": "Export-only working-copy plan ready",
            "planner": {"planner_type": "deterministic", "planner_is_ai": False},
            "actions": [
                {"operation": "export", "target": record.file_id, "value": value}
                for value in (record.export_formats or [])
            ],
            "risk": "LOW_RISK",
            "review_required": False,
            "policy_errors": [],
            "can_approve": can_approve,
            "canceled": record.canceled,
            "executed": record.execution is not None,
        }
    if record.result is None:
        raise RuntimeError("mutation record has no planning result")
    envelope = record.result.envelope
    actions = []
    if envelope is not None:
        for action in envelope.plan.actions:
            actions.append(
                {
                    "operation": action.operation.value,
                    "target": action.target.value,
                    "target_kind": action.target.kind.value,
                    "object_type": action.target.object_type,
                    "value": action.value,
                }
            )
    validation = record.validation or {}
    visible_status = record.result.status
    if visible_status == "PLANNED" and validation.get("review_required"):
        visible_status = "NEEDS_REVIEW"
    can_approve = bool(
        record.result.status == "PLANNED"
        and validation.get("accepted")
        and validation.get("risk_level") == "LOW_RISK"
        and not validation.get("review_required")
        and not record.canceled
        and not record.executing
        and record.execution is None
    )
    return {
        "task_id": record.task_id,
        "file_id": record.file_id,
        "kind": record.kind,
        "status": visible_status,
        "message": record.result.message,
        "planner": (
            envelope.provenance.model_dump(mode="json") if envelope is not None else None
        ),
        "actions": actions,
        "risk": validation.get("risk_level", "DISALLOWED"),
        "review_required": validation.get("review_required", True),
        "policy_errors": validation.get("errors", []),
        "can_approve": can_approve,
        "canceled": record.canceled,
        "executed": record.execution is not None,
    }


def _create_diff(before: Path, after: Path, destination: Path) -> Path:
    with Image.open(before).convert("RGB") as left, Image.open(after).convert("RGB") as right:
        if left.size != right.size:
            raise ValueError("before and after previews use different dimensions")
        diff = ImageEnhance.Contrast(ImageChops.difference(left, right)).enhance(4.0)
        diff.save(destination, format="PNG")
    return destination


def create_corel_codex_ui_app(
    *,
    service: OperatorToolService,
    planner: PlanBroker,
    workspace: Path,
    health_probe: HealthProbe | None = None,
    path_opener: PathOpener = open_local_path,
    lifecycle_callback: Callable[[Literal["shutdown", "restart"]], None] | None = None,
) -> FastAPI:
    """Create the loopback UI API over the existing safe operator service."""

    approved_workspace = workspace.resolve()
    approved_workspace.mkdir(parents=True, exist_ok=True)
    settings_store = UiSettingsStore(approved_workspace / "corel_ui_settings.json")
    job_store = UiJobStore(approved_workspace / "corel_ui_jobs.sqlite")
    output_manager = UiOutputManager(approved_workspace)
    records: dict[str, _PlanRecord] = {}
    lock = threading.RLock()
    app = FastAPI(title="Corel AI Operator", version="1.0")

    def record(task_id: str) -> _PlanRecord:
        with lock:
            value = records.get(task_id)
        if value is None:
            raise HTTPException(status_code=404, detail="plan task was not found")
        return value

    @app.get("/corel-ui", response_class=HTMLResponse)
    def ui_page() -> str:
        return COREL_UI_HTML

    @app.get("/api/v1/corel-ui/status")
    def status() -> dict[str, Any]:
        payload = health_probe.probe() if health_probe is not None else {
            "status": "READY",
            "components": {
                key: {"status": "READY", "message": "injected test service"}
                for key in ("corel", "mcp", "operator", "codex")
            },
        }
        return {
            **payload,
            "local_only": True,
            "source_policy": "READ_ONLY",
            "mutation_authority": "EXPLICIT_APPROVAL_WORKING_COPY_ONLY",
            "planner": "Codex CLI via read-only Corel MCP",
        }

    @app.get("/api/v1/corel-ui/settings")
    def get_settings() -> dict[str, Any]:
        return settings_store.load().model_dump(mode="json")

    @app.put("/api/v1/corel-ui/settings")
    def put_settings(request: UiSettingsV1) -> dict[str, Any]:
        return settings_store.save(request).model_dump(mode="json")

    @app.get("/api/v1/corel-ui/jobs")
    def recent_jobs() -> dict[str, Any]:
        settings = settings_store.load()
        jobs = job_store.list_recent(settings.recent_job_limit)
        return {"count": len(jobs), "jobs": [_stored_job_summary(item) for item in jobs]}

    @app.get("/api/v1/corel-ui/jobs/{task_id}")
    def stored_job(task_id: str) -> dict[str, Any]:
        try:
            value = job_store.get(task_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="job was not found") from exc
        return _stored_job_summary(value)

    @app.post("/api/v1/corel-ui/document")
    def inspect_document(request: UiDocumentRequestV1) -> dict[str, Any]:
        try:
            document = service.get_document(request.file_id)
        except Exception as exc:
            raise HTTPException(status_code=422, detail="document inspection failed") from exc
        return {
            "file_id": request.file_id,
            "page_count": document["page_count"],
            "object_count": document["object_count"],
            "text_object_count": document["text_object_count"],
            "bitmap_count": document["bitmap_count"],
            "vector_count": document["vector_count"],
            "group_count": document["group_count"],
            "corel_version": document["corel_version"],
            "inspection_status": "PASS",
            "source_policy": "READ_ONLY",
        }

    @app.post("/api/v1/corel-ui/plan")
    def plan(request: UiPlanRequestV1) -> dict[str, Any]:
        task_id = "ui-" + uuid.uuid4().hex[:20]
        command_analysis = analyze_vietnamese_command(request.instruction)
        is_export_only = (
            command_analysis.disposition == "OUTPUT_ONLY_UNSUPPORTED"
            and bool(command_analysis.output_formats)
            and all(
                token in {"xuất", "export", "file", "pdf", "png", "cdr", "và", ","}
                for token in re.findall(r"[\wÀ-ỹ]+|,", request.instruction.casefold())
            )
        )
        result: CodexPlanningResultV1 | None = None
        if not is_export_only:
            try:
                result = planner.plan(
                    file_id=request.file_id,
                    task_id=task_id,
                    instruction=request.instruction,
                )
            except CodexPlannerUnavailable as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from exc
        validation_payload: dict[str, Any] | None = None
        if result is not None and result.envelope is not None:
            validation = validate_agent_plan(
                CorelAgentRequestV1(
                    request_id=task_id,
                    document_id=request.file_id,
                    instruction=request.instruction,
                    execution_mode="PLAN_ONLY",
                ),
                result.envelope,
            )
            validation_payload = validation.model_dump(mode="json")
            if not validation.accepted:
                result = CodexPlanningResultV1(
                    status="REJECTED",
                    message="Plan was rejected by the operator policy",
                )
                validation_payload = validation.model_dump(mode="json")
        value = _PlanRecord(
            task_id=task_id,
            file_id=request.file_id,
            instruction=request.instruction,
            result=result,
            validation=validation_payload,
            kind="EXPORT_ONLY" if is_export_only else "MUTATION",
            export_formats=(
                list(command_analysis.output_formats) if is_export_only else None
            ),
        )
        with lock:
            records[task_id] = value
        summary = _plan_summary(value)
        job_store.create(
            task_id=task_id,
            file_id=request.file_id,
            instruction=request.instruction,
            kind=value.kind,
            status=summary["status"],
            message=summary["message"],
        )
        return summary

    @app.post("/api/v1/corel-ui/approve")
    def approve(request: UiApprovalRequestV1) -> dict[str, Any]:
        value = record(request.task_id)
        with lock:
            if value.canceled:
                raise HTTPException(status_code=409, detail="plan was canceled")
            if value.executing:
                raise HTTPException(status_code=409, detail="plan execution is already running")
            if value.execution is not None:
                raise HTTPException(status_code=409, detail="plan was already executed")
            if not _plan_summary(value)["can_approve"]:
                raise HTTPException(status_code=409, detail="plan is not eligible for execution")
            if value.kind == "MUTATION":
                if value.result is None or value.result.envelope is None:
                    raise HTTPException(status_code=409, detail="validated plan is missing")
                confirmed_validation = validate_agent_plan(
                    CorelAgentRequestV1(
                        request_id=value.task_id,
                        document_id=value.file_id,
                        instruction=value.instruction,
                        execution_mode="EXECUTE_CONFIRMED",
                    ),
                    value.result.envelope,
                )
                if not confirmed_validation.execution_allowed:
                    raise HTTPException(status_code=409, detail="operator policy denied execution")
            value.executing = True
            job_store.update(value.task_id, status="EXECUTING", message="Working-copy task is running")
        try:
            if value.kind == "EXPORT_ONLY":
                execution = service.export_copy(
                    value.file_id,
                    task_id=value.task_id,
                    formats=value.export_formats or ["CDR"],
                )
                visual_qa = execution.get("metadata", {}).get("visual_qa_v2")
            else:
                assert value.result is not None and value.result.envelope is not None
                execution = service.execute_plan(
                    value.file_id,
                    task_id=value.task_id,
                    plan=value.result.envelope.plan,
                )
                visual_qa = (
                    service.visual_qa(task_id=value.task_id)
                    if execution.get("preview_before") and execution.get("preview_after")
                    else None
                )
        except Exception as exc:
            with lock:
                value.executing = False
            job_store.update(
                value.task_id,
                status="FAILED",
                qa_status="FAILED",
                message="Operator failed safely; inspect debug details and retry with a new job",
            )
            raise HTTPException(status_code=500, detail="operator execution failed safely") from exc
        if execution.get("source_unchanged") is not True:
            with lock:
                value.executing = False
                value.canceled = True
            job_store.update(
                value.task_id,
                status="FAILED",
                qa_status="FAILED",
                source_unchanged=False,
                message="Source immutability verification failed; stop using the operator",
            )
            raise HTTPException(status_code=500, detail="immutable source verification failed")
        task_root = (approved_workspace / "runs" / value.task_id).resolve(strict=False)
        before = task_root / "working_copy_before.png"
        after = task_root / "working_copy_after.png"
        payload = {**execution, "visual_qa": visual_qa}
        try:
            if before.is_file() and after.is_file():
                _create_diff(before, after, task_root / "working_copy_diff.png")
            output_version, outputs = output_manager.publish(
                value.task_id, settings_store.load()
            )
        except Exception as exc:
            with lock:
                value.executing = False
                value.canceled = True
            job_store.update(
                value.task_id,
                status="FAILED",
                qa_status="FAILED",
                source_unchanged=True,
                message="Working copy completed but output post-processing failed",
            )
            raise HTTPException(status_code=500, detail="output post-processing failed") from exc
        with lock:
            value.executing = False
            value.execution = payload
            value.output_version = output_version
            value.outputs = outputs
        summary = _execution_summary(value)
        job_store.update(
            value.task_id,
            status=summary["status"],
            qa_status=summary["qa"]["status"],
            message=summary["recovery"]["message"],
            source_unchanged=summary["source_unchanged"],
            rollback_verified=summary["rollback_verified"],
            output_version=output_version,
            outputs=outputs,
        )
        return summary

    @app.post("/api/v1/corel-ui/cancel")
    def cancel(request: UiCancelRequestV1) -> dict[str, Any]:
        value = record(request.task_id)
        with lock:
            if value.executing:
                raise HTTPException(
                    status_code=409,
                    detail="job is active; operator will finish or rollback before shutdown",
                )
            if value.execution is not None:
                raise HTTPException(
                    status_code=409,
                    detail="completed working copies are preserved; post-commit undo is unsupported",
                )
            value.canceled = True
            job_store.update(
                value.task_id,
                status="CANCELED",
                message="Canceled before execution; source remains read-only",
                source_unchanged=True,
            )
        return {"task_id": value.task_id, "status": "CANCELED", "source_unchanged": True}

    @app.post("/api/v1/corel-ui/rollback")
    def rollback(request: UiCancelRequestV1) -> dict[str, Any]:
        value = record(request.task_id)
        if value.executing:
            raise HTTPException(
                status_code=409,
                detail="active transaction owns rollback; wait for its terminal result",
            )
        if value.execution is None:
            with lock:
                value.canceled = True
            job_store.update(
                value.task_id,
                status="CANCELED",
                message="Canceled before execution; source remains read-only",
                source_unchanged=True,
            )
            return {"task_id": value.task_id, "status": "CANCELED_BEFORE_EXECUTION"}
        execution = value.execution
        return {
            "task_id": value.task_id,
            "status": "AUTO_ROLLBACK_ONLY",
            "rollback_verified": bool(execution.get("rollback_verified")),
            "message": "The operator auto-rolls back failed transactions; committed copies are preserved.",
        }

    @app.get("/api/v1/corel-ui/task/{task_id}")
    def task(task_id: str) -> dict[str, Any]:
        if not _TASK_ID_RE.fullmatch(task_id):
            raise HTTPException(status_code=404, detail="task not found")
        with lock:
            value = records.get(task_id)
        if value is not None:
            return _execution_summary(value) if value.execution else _plan_summary(value)
        try:
            return _stored_job_summary(job_store.get(task_id))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="task not found") from exc

    @app.post("/api/v1/corel-ui/open")
    def open_output(request: UiOpenRequestV1) -> dict[str, Any]:
        try:
            stored = job_store.get(request.task_id)
            path = (
                output_manager.resolve_folder(stored.outputs)
                if request.kind == "folder"
                else output_manager.resolve(stored.outputs[request.kind])
            )
            path_opener(path)
        except (KeyError, FileNotFoundError, ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=404, detail="requested local output is unavailable") from exc
        return {"task_id": request.task_id, "kind": request.kind, "opened": True}

    @app.post("/api/v1/corel-ui/lifecycle")
    def lifecycle(request: UiLifecycleRequestV1) -> dict[str, Any]:
        with lock:
            active = [item.task_id for item in records.values() if item.executing]
        if active:
            raise HTTPException(
                status_code=409,
                detail="active job must finish or rollback before service lifecycle change",
            )
        if lifecycle_callback is None:
            return {
                "status": "SAFE_TO_STOP",
                "action": request.action,
                "message": "Use Ctrl+C in the launcher window to stop safely",
            }
        threading.Timer(0.25, lifecycle_callback, args=(request.action,)).start()
        return {"status": f"{request.action.upper()}_REQUESTED", "active_jobs": 0}

    @app.get("/api/v1/corel-ui/artifact/{task_id}/{kind}")
    def artifact(task_id: str, kind: str) -> FileResponse:
        if not _TASK_ID_RE.fullmatch(task_id):
            raise HTTPException(status_code=404, detail="artifact not found")
        names = {
            "before": ("image/png", False),
            "after": ("image/png", False),
            "diff": ("image/png", False),
            "png": ("image/png", True),
            "pdf": ("application/pdf", True),
            "cdr": ("application/octet-stream", True),
        }
        selected = names.get(kind)
        if selected is None:
            raise HTTPException(status_code=404, detail="artifact not found")
        try:
            stored = job_store.get(task_id)
            path = output_manager.resolve(stored.outputs[kind])
        except (KeyError, FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=404, detail="artifact not found") from exc
        media_type, download = selected
        return FileResponse(
            path,
            media_type=media_type,
            filename=path.name if download else None,
            headers={"Cache-Control": "no-store"},
        )

    return app


def _execution_summary(record: _PlanRecord) -> dict[str, Any]:
    execution = record.execution or {}
    visual = execution.get("visual_qa") or execution.get("metadata", {}).get("visual_qa_v2") or {}
    status = execution.get("result", "FAILED")
    source_unchanged = bool(execution.get("source_unchanged", False))
    rollback_verified = bool(execution.get("rollback_verified", False))
    if source_unchanged and status == "AUTO_SUCCESS":
        recovery = {
            "code": "NONE",
            "message": "Completed safely; versioned working-copy outputs are ready",
            "recommended_action": "Open or download the generated CDR/PDF/PNG",
        }
    elif source_unchanged and status == "NEEDS_REVIEW":
        recovery = {
            "code": execution.get("error_code") or "QA_REVIEW",
            "message": "Working copy needs review; source remains safe",
            "recommended_action": "Inspect Before/After/Diff and create a new bounded job",
        }
    else:
        recovery = {
            "code": execution.get("error_code") or "SAFE_FAILURE",
            "message": "Job failed; source safety is shown separately",
            "recommended_action": "Check debug details and retry only with a new job",
        }
    return {
        "task_id": record.task_id,
        "kind": record.kind,
        "status": status,
        "operation_count": execution.get("operation_count", 0),
        "source_unchanged": source_unchanged,
        "transaction_committed": execution.get("transaction_committed", False),
        "rollback_verified": rollback_verified,
        "editability_verified": execution.get("editability_verified", False),
        "save_completed": execution.get("metadata", {}).get("save_completed", False),
        "reopen_completed": execution.get("metadata", {}).get("reopen_completed", False),
        "output_version": record.output_version,
        "qa": {
            "status": visual.get("status", "FAILED"),
            "reasons": visual.get("reasons", visual.get("issues", [])),
        },
        "recovery": recovery,
        "artifacts": {
            name: f"/api/v1/corel-ui/artifact/{record.task_id}/{name}"
            for name in (record.outputs or {})
        },
    }


def _stored_job_summary(record: UiJobRecordV1) -> dict[str, Any]:
    return {
        "task_id": record.task_id,
        "file_id": record.file_id,
        "instruction": record.instruction,
        "kind": record.kind,
        "status": record.status,
        "qa_status": record.qa_status,
        "message": record.message,
        "source_unchanged": record.source_unchanged,
        "rollback_verified": record.rollback_verified,
        "output_version": record.output_version,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
        "artifacts": {
            name: f"/api/v1/corel-ui/artifact/{record.task_id}/{name}"
            for name in record.outputs
        },
        "open_actions": (
            ["folder", *[name for name in ("cdr", "pdf", "png") if name in record.outputs]]
            if record.outputs
            else []
        ),
    }


COREL_UI_HTML = r"""<!doctype html>
<html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Corel Codex · Safe Operator</title><style>
:root{color-scheme:dark;--bg:#101214;--panel:#1a1e21;--panel2:#20262a;--line:#30383d;--text:#eef2f3;--muted:#9eaaaf;--cyan:#64d8cb;--amber:#f3c76a;--red:#ff7b7b;--green:#70d49b}
*{box-sizing:border-box}body{margin:0;background:linear-gradient(135deg,#0c1012,#151a1d);color:var(--text);font:14px system-ui,Segoe UI,sans-serif;min-height:100vh}
header{height:62px;padding:0 22px;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid var(--line);background:#111618e8;position:sticky;top:0;z-index:3}
header strong{letter-spacing:.08em}.safe{color:var(--green);font-size:12px}.shell{display:grid;grid-template-columns:320px minmax(420px,1fr);gap:16px;max-width:1720px;margin:auto;padding:16px}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:16px;box-shadow:0 14px 34px #0004}.sidebar{display:grid;gap:16px;align-content:start}.workspace{display:grid;gap:16px}
h2{font-size:12px;text-transform:uppercase;letter-spacing:.13em;color:var(--muted);margin:0 0 13px}h3{margin:0;font-size:18px}.field{display:grid;gap:7px;margin-bottom:12px}label{color:var(--muted);font-size:12px}
input,textarea{width:100%;border:1px solid var(--line);background:#0e1214;color:var(--text);border-radius:8px;padding:11px;font:inherit}textarea{min-height:92px;resize:vertical}
button,.button{border:1px solid var(--line);background:#263036;color:var(--text);border-radius:8px;padding:10px 13px;font-weight:700;cursor:pointer;text-decoration:none;display:inline-flex;align-items:center;justify-content:center;gap:7px}button:hover,.button:hover{filter:brightness(1.15)}button:disabled,.button.disabled{opacity:.35;pointer-events:none}.primary{background:#175c57;border-color:#27877f}.danger{border-color:#754444}.actions{display:flex;gap:9px;flex-wrap:wrap}
.source-lock{padding:10px;border:1px solid #2f6552;background:#172b25;border-radius:8px;color:#9ae1bd;font-weight:700}.working{margin-top:8px;color:var(--muted)}.health{display:flex;gap:7px;flex-wrap:wrap;justify-content:flex-end}.health .badge{border:1px solid var(--line)}
.stats{display:grid;grid-template-columns:1fr 1fr;gap:8px}.stat{background:var(--panel2);border-radius:8px;padding:10px}.stat b{display:block;font-size:19px}.stat span{color:var(--muted);font-size:11px}
.top-grid{display:grid;grid-template-columns:1.05fr .95fr;gap:16px}.plan{min-height:260px}.empty{color:var(--muted);display:grid;place-items:center;min-height:120px;text-align:center}.badge{display:inline-flex;padding:5px 8px;border-radius:999px;background:#30383d;font-size:11px;font-weight:800}.badge.pass{background:#17462e;color:#9ae1bd}.badge.review{background:#513f19;color:#f6d889}.badge.fail{background:#512626;color:#ffaaaa}
.plan-row{display:grid;grid-template-columns:110px 1fr;gap:9px;padding:8px 0;border-bottom:1px solid var(--line)}.plan-row span:first-child{color:var(--muted)}.command-log{margin-top:12px;padding-top:12px;border-top:1px solid var(--line);color:var(--muted);max-height:88px;overflow:auto}.presets{display:flex;gap:6px;flex-wrap:wrap;margin:0 0 12px}.preset{font-size:11px;padding:7px 9px;background:#202a2f}.job{padding:10px 0;border-bottom:1px solid var(--line);cursor:pointer}.job:last-child{border:0}.job strong{display:block}.job small{color:var(--muted)}.settings-grid{display:grid;gap:9px}.settings-grid label{display:flex;justify-content:space-between;gap:12px;align-items:center}.settings-grid input[type=text],.settings-grid select{max-width:145px;background:#0e1214;color:var(--text);border:1px solid var(--line);border-radius:6px;padding:6px}.recovery{padding:10px;border-radius:8px;background:#151b1f;margin-top:10px;color:var(--muted)}
.qa{display:grid;grid-template-columns:180px 1fr;gap:14px;align-items:center}.qa-status{font-size:25px;font-weight:900}.preview-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}.preview{background:#0d1011;border:1px solid var(--line);border-radius:9px;overflow:hidden}.preview h3{font-size:12px;padding:9px 11px;color:var(--muted)}.preview-frame{height:48vh;min-height:300px;background:#d9dcda;display:grid;place-items:center}.preview img{max-width:100%;max-height:100%;object-fit:contain}.outputs{display:flex;gap:9px;flex-wrap:wrap}.agent-message{padding:10px 12px;border-left:3px solid var(--cyan);background:#142326;color:#cbe7e4;border-radius:0 8px 8px 0;margin-top:10px}details{margin-top:12px;color:var(--muted)}pre{white-space:pre-wrap;word-break:break-word;background:#0d1113;padding:10px;border-radius:7px;font-size:11px}
@media(max-width:1050px){.shell{grid-template-columns:1fr}.top-grid{grid-template-columns:1fr}.preview-grid{grid-template-columns:1fr}.preview-frame{height:55vh}}
</style></head><body>
<header><strong>COREL AI OPERATOR · V1</strong><div id="healthBar" class="health"><span class="badge">HEALTH CHECK…</span></div></header>
<main class="shell"><aside class="sidebar">
<section class="panel"><h2>Document</h2><div class="source-lock">SOURCE FILE: READ ONLY</div><div class="working" id="working">WORKING COPY: chưa tạo</div><div class="field" style="margin-top:14px"><label>Safe inventory/document ID</label><input id="fileId" placeholder="file:…" value="file:2af26b5496e33f1a4e00f2360ccc7909"></div><button id="inspect" class="primary">Inspect document</button><div id="documentMeta" class="empty">Chưa inspect document</div></section>
<section class="panel"><h2>Execution controls</h2><div class="actions"><button id="approve" class="primary" disabled>Approve</button><button id="cancel" disabled>Cancel</button><button id="rollback" class="danger" disabled>Undo / Rollback</button></div><p class="working">Mutation chỉ chạy sau khi bạn bấm Approve. Failure tự rollback trong transaction.</p><div class="actions" style="margin-top:12px"><button id="restart">Restart service</button><button id="shutdown">Safe shutdown</button></div></section>
<section class="panel"><h2>Outputs</h2><div id="outputs" class="outputs"><span class="empty">Chưa có output</span></div></section>
<section class="panel"><h2>Recent jobs</h2><div id="jobs"><span class="empty">Chưa có job</span></div></section>
<section class="panel"><h2>Settings</h2><div class="settings-grid"><label>Output folder<input id="outputFolder" type="text" value="jobs"></label><label>PDF default<input id="defaultPdf" type="checkbox" checked></label><label>PNG default<input id="defaultPng" type="checkbox" checked></label><label>Preview<select id="previewQuality"><option value="high">High</option><option value="standard">Standard</option></select></label><label>Recent limit<input id="recentLimit" type="text" value="20"></label><button id="saveSettings">Save settings</button></div></section>
</aside><section class="workspace">
<div class="top-grid"><section class="panel"><h2>Chat / command</h2><div class="presets" id="presets"><button class="preset" data-template='Đổi "NỘI DUNG CŨ" thành "NỘI DUNG MỚI"'>Đổi tên/text</button><button class="preset" data-template="Đổi số điện thoại 0900 000 000 thành 0909 111 222">Đổi số điện thoại</button><button class="preset" data-template='Đổi "ĐỊA CHỈ CŨ" thành "ĐỊA CHỈ MỚI"'>Đổi địa chỉ</button><button class="preset" data-template="Đổi giá 30K thành 35K">Đổi giá</button><button class="preset" data-template="Di chuyển object_ID sang phải 1mm">Move object</button><button class="preset" data-template="Tăng object_ID lên 5%">Resize object</button><button class="preset" data-template="Xuất PDF">Export PDF</button><button class="preset" data-template="Xuất PNG">Export PNG</button></div><div class="field"><label>Yêu cầu tiếng Việt</label><textarea id="instruction" placeholder="Ví dụ: Đổi nội dung của object…"></textarea></div><button id="planButton" class="primary" disabled>Ask Codex to plan</button><div id="agentMessage" class="agent-message">Inspect document trước khi lập plan.</div><div id="recent" class="command-log">Recent commands: —</div></section>
<section class="panel plan"><h2>Plan preview</h2><div id="planPanel" class="empty">Plan sẽ hiển thị ở đây trước execution.</div><details><summary>Debug details</summary><pre id="debug">—</pre></details></section></div>
<section class="panel"><h2>Visual QA</h2><div class="qa"><div id="qaStatus" class="qa-status">WAITING</div><div><div id="qaReason" class="working">Chưa có execution.</div><div id="recovery" class="recovery">Source luôn read-only; mọi output là working copy có version.</div></div></div></section>
<section class="panel"><h2>Before / After / Diff</h2><div class="preview-grid"><article class="preview"><h3>BEFORE</h3><div class="preview-frame"><img id="before" alt="Before preview"></div></article><article class="preview"><h3>AFTER</h3><div class="preview-frame"><img id="after" alt="After preview"></div></article><article class="preview"><h3>DIFF</h3><div class="preview-frame"><img id="diff" alt="Diff preview"></div></article></div></section>
</section></main><script>
const $=id=>document.getElementById(id);let currentTask=null,recent=[];
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function api(path,options={}){const response=await fetch(path,{headers:{'Content-Type':'application/json'},...options});const data=await response.json().catch(()=>({detail:response.statusText}));if(!response.ok)throw new Error(data.detail||response.statusText);return data}
function busy(message){$('agentMessage').textContent=message}
function showError(error){busy(error.message);$('qaStatus').textContent='FAILED';$('qaStatus').className='qa-status fail';$('qaReason').textContent=error.message;$('recovery').textContent='Mutation không được tiếp tục. Kiểm tra Corel/health rồi tạo job mới; source vẫn được kiểm tra read-only.'}
async function loadHealth(){try{const h=await api('/api/v1/corel-ui/status');$('healthBar').innerHTML=Object.entries(h.components).map(([name,value])=>'<span class="badge '+(value.status==='READY'?'pass':'fail')+'" title="'+esc(value.message)+'">'+esc(name.toUpperCase())+' '+esc(value.status)+'</span>').join('')}catch(e){$('healthBar').innerHTML='<span class="badge fail">HEALTH OFFLINE</span>'}}
async function loadSettings(){const s=await api('/api/v1/corel-ui/settings');$('outputFolder').value=s.output_subfolder;$('defaultPdf').checked=s.default_pdf_export;$('defaultPng').checked=s.default_png_export;$('previewQuality').value=s.preview_quality;$('recentLimit').value=s.recent_job_limit}
$('saveSettings').onclick=async()=>{try{await api('/api/v1/corel-ui/settings',{method:'PUT',body:JSON.stringify({output_subfolder:$('outputFolder').value,default_pdf_export:$('defaultPdf').checked,default_png_export:$('defaultPng').checked,preview_quality:$('previewQuality').value,recent_job_limit:Number($('recentLimit').value)})});busy('Settings đã lưu local.')}catch(e){showError(e)}};
document.querySelectorAll('.preset').forEach(button=>button.onclick=()=>{$('instruction').value=button.dataset.template;$('instruction').focus()});
$('inspect').onclick=async()=>{try{busy('Đang inspect Corel document ở chế độ read-only…');const d=await api('/api/v1/corel-ui/document',{method:'POST',body:JSON.stringify({file_id:$('fileId').value.trim()})});$('documentMeta').className='stats';$('documentMeta').innerHTML='<div class="stat"><b>'+d.page_count+'</b><span>pages</span></div><div class="stat"><b>'+d.object_count+'</b><span>objects</span></div><div class="stat"><b>'+d.text_object_count+'</b><span>editable text</span></div><div class="stat"><b>'+d.vector_count+'</b><span>vectors</span></div>';$('planButton').disabled=false;busy('Inspection PASS · '+d.corel_version)}catch(e){showError(e)}};
$('planButton').onclick=async()=>{const instruction=$('instruction').value.trim();if(!instruction)return;try{$('planButton').disabled=true;busy('Codex đang inspect qua MCP và lập bounded plan…');const p=await api('/api/v1/corel-ui/plan',{method:'POST',body:JSON.stringify({file_id:$('fileId').value.trim(),instruction})});currentTask=p.task_id;recent.unshift(instruction);$('recent').textContent='Recent commands: '+recent.slice(0,4).join(' · ');renderPlan(p);await loadJobs()}catch(e){showError(e)}finally{$('planButton').disabled=false}};
function renderPlan(p){const badge=p.status==='PLANNED'?'pass':p.status==='NEEDS_REVIEW'?'review':'fail';$('planPanel').className='';$('planPanel').innerHTML='<div class="actions"><span class="badge '+badge+'">'+esc(p.status)+'</span><span class="badge">RISK '+esc(p.risk)+'</span><span class="badge">'+esc(p.kind)+'</span></div>'+(p.actions.length?p.actions.map(a=>'<div class="plan-row"><span>'+esc(a.operation)+'</span><div><b>'+esc(a.target)+'</b><br><span class="working">'+esc(JSON.stringify(a.value))+'</span></div></div>').join(''):'<div class="empty">Không có executable action.</div>');$('debug').textContent=JSON.stringify(p,null,2);$('approve').disabled=!p.can_approve;$('cancel').disabled=false;$('rollback').disabled=false;busy(p.message+(p.can_approve?' · Chờ bạn Approve.':' · Job bị giữ lại.'));$('qaStatus').textContent=p.status;$('qaStatus').className='qa-status '+badge;$('qaReason').textContent=(p.policy_errors||[]).join(', ')||'Plan-only; chưa mutation.';$('recovery').textContent=p.can_approve?'Kiểm tra plan rồi bấm Approve. Source vẫn read-only.':'Không execute. Làm rõ target/value hoặc chọn object ID ổn định.'}
$('approve').onclick=async()=>{if(!currentTask)return;try{$('approve').disabled=true;$('cancel').disabled=true;busy('Đã Approve. Operator đang tạo working copy, transaction, QA và save/reopen…');const x=await api('/api/v1/corel-ui/approve',{method:'POST',body:JSON.stringify({task_id:currentTask,approved:true})});renderExecution(x);await loadJobs()}catch(e){showError(e)}};
function outputButtons(taskId,artifacts){const downloads=Object.entries(artifacts).filter(([kind])=>['cdr','pdf','png'].includes(kind)).map(([kind,url])=>'<a class="button" href="'+url+'">Download '+kind.toUpperCase()+'</a>');const opens=['folder',...Object.keys(artifacts).filter(kind=>['cdr','pdf','png'].includes(kind))].map(kind=>'<button onclick="openOutput(\''+taskId+'\',\''+kind+'\')">Open '+(kind==='folder'?'folder':kind.toUpperCase())+'</button>');return [...downloads,...opens].join('')}
function showArtifacts(artifacts){['before','after','diff'].forEach(kind=>{$(kind).src=artifacts[kind]?artifacts[kind]+'?v='+Date.now():''})}
function renderExecution(x){$('working').textContent='WORKING COPY: '+x.status+' · editable='+x.editability_verified+' · v'+String(x.output_version||1).padStart(3,'0');$('qaStatus').textContent=x.qa.status;$('qaStatus').className='qa-status '+(x.qa.status==='PASS'?'pass':x.qa.status==='NEEDS_REVIEW'?'review':'fail');$('qaReason').textContent=(x.qa.reasons||[]).join(', ')||'Không có reason code.';$('recovery').textContent=x.recovery.message+' · '+x.recovery.recommended_action;showArtifacts(x.artifacts);$('outputs').innerHTML=outputButtons(x.task_id,x.artifacts);$('rollback').disabled=false;busy(x.status+' · save='+x.save_completed+' · reopen='+x.reopen_completed+' · source unchanged='+x.source_unchanged);$('debug').textContent=JSON.stringify(x,null,2)}
async function openOutput(taskId,kind){try{await api('/api/v1/corel-ui/open',{method:'POST',body:JSON.stringify({task_id:taskId,kind})});busy('Đã mở '+kind+' local.')}catch(e){showError(e)}}
window.openOutput=openOutput;
async function loadJobs(){try{const data=await api('/api/v1/corel-ui/jobs');$('jobs').innerHTML=data.jobs.length?data.jobs.map(job=>'<div class="job" data-task="'+esc(job.task_id)+'"><strong>'+esc(job.status)+' · '+esc(job.qa_status)+'</strong><small>'+esc(new Date(job.updated_at).toLocaleString())+' · '+esc(job.instruction)+'</small></div>').join(''):'<span class="empty">Chưa có job</span>';document.querySelectorAll('.job').forEach(node=>node.onclick=()=>loadJob(node.dataset.task))}catch(e){showError(e)}}
async function loadJob(taskId){try{const job=await api('/api/v1/corel-ui/jobs/'+taskId);currentTask=taskId;$('fileId').value=job.file_id;$('instruction').value=job.instruction;$('working').textContent='WORKING COPY: '+job.status+(job.output_version?' · v'+String(job.output_version).padStart(3,'0'):'');$('qaStatus').textContent=job.qa_status;$('qaStatus').className='qa-status '+(job.qa_status==='PASS'?'pass':job.qa_status==='NEEDS_REVIEW'?'review':'fail');$('qaReason').textContent=job.message;$('recovery').textContent=job.source_unchanged===false?'STOP: source safety failed.':'Job local đã được khôi phục từ history.';showArtifacts(job.artifacts);$('outputs').innerHTML=outputButtons(job.task_id,job.artifacts);$('debug').textContent=JSON.stringify(job,null,2)}catch(e){showError(e)}}
$('cancel').onclick=async()=>{if(!currentTask)return;try{const x=await api('/api/v1/corel-ui/cancel',{method:'POST',body:JSON.stringify({task_id:currentTask})});busy(x.status);$('approve').disabled=true;$('cancel').disabled=true;await loadJobs()}catch(e){showError(e)}};
$('rollback').onclick=async()=>{if(!currentTask)return;try{const x=await api('/api/v1/corel-ui/rollback',{method:'POST',body:JSON.stringify({task_id:currentTask})});busy(x.message||x.status);$('debug').textContent=JSON.stringify(x,null,2)}catch(e){showError(e)}};
async function lifecycle(action){try{const x=await api('/api/v1/corel-ui/lifecycle',{method:'POST',body:JSON.stringify({action})});busy(x.message||x.status)}catch(e){showError(e)}}
$('restart').onclick=()=>lifecycle('restart');$('shutdown').onclick=()=>lifecycle('shutdown');
Promise.all([loadHealth(),loadSettings(),loadJobs()]).catch(showError);
</script></body></html>"""


__all__ = [
    "CodexCliPlanBroker",
    "CodexPlannerUnavailable",
    "CodexPlanningResultV1",
    "PlanBroker",
    "create_corel_codex_ui_app",
]
