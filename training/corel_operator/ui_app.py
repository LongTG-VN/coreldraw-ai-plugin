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
from typing import Any, Literal, Protocol

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
Use one action with the requested bounded operation/value and an object_id selector
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
    result: CodexPlanningResultV1
    validation: dict[str, Any] | None
    canceled: bool = False
    executing: bool = False
    execution: dict[str, Any] | None = None


def _plan_summary(record: _PlanRecord) -> dict[str, Any]:
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
        "status": record.result.status,
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
) -> FastAPI:
    """Create the loopback UI API over the existing safe operator service."""

    approved_workspace = workspace.resolve()
    approved_workspace.mkdir(parents=True, exist_ok=True)
    records: dict[str, _PlanRecord] = {}
    lock = threading.RLock()
    app = FastAPI(title="Corel Codex UI", version="0.1-mvp")

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
        return {
            "status": "READY",
            "local_only": True,
            "source_policy": "READ_ONLY",
            "mutation_authority": "EXPLICIT_APPROVAL_WORKING_COPY_ONLY",
            "planner": "Codex CLI via read-only Corel MCP",
        }

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
        try:
            result = planner.plan(
                file_id=request.file_id,
                task_id=task_id,
                instruction=request.instruction,
            )
        except CodexPlannerUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        validation_payload: dict[str, Any] | None = None
        if result.envelope is not None:
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
        )
        with lock:
            records[task_id] = value
        return _plan_summary(value)

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
            if not _plan_summary(value)["can_approve"] or value.result.envelope is None:
                raise HTTPException(status_code=409, detail="plan is not eligible for execution")
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
        try:
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
            raise HTTPException(status_code=500, detail="operator execution failed safely") from exc
        if execution.get("source_unchanged") is not True:
            with lock:
                value.executing = False
                value.canceled = True
            raise HTTPException(status_code=500, detail="immutable source verification failed")
        task_root = (approved_workspace / "runs" / value.task_id).resolve(strict=False)
        before = task_root / "working_copy_before.png"
        after = task_root / "working_copy_after.png"
        if before.is_file() and after.is_file():
            _create_diff(before, after, task_root / "working_copy_diff.png")
        payload = {**execution, "visual_qa": visual_qa}
        with lock:
            value.executing = False
            value.execution = payload
        return _execution_summary(value)

    @app.post("/api/v1/corel-ui/cancel")
    def cancel(request: UiCancelRequestV1) -> dict[str, Any]:
        value = record(request.task_id)
        with lock:
            if value.execution is not None:
                raise HTTPException(
                    status_code=409,
                    detail="completed working copies are preserved; post-commit undo is unsupported",
                )
            value.canceled = True
        return {"task_id": value.task_id, "status": "CANCELED", "source_unchanged": True}

    @app.post("/api/v1/corel-ui/rollback")
    def rollback(request: UiCancelRequestV1) -> dict[str, Any]:
        value = record(request.task_id)
        if value.execution is None:
            with lock:
                value.canceled = True
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
        value = record(task_id)
        return _execution_summary(value) if value.execution else _plan_summary(value)

    @app.get("/api/v1/corel-ui/artifact/{task_id}/{kind}")
    def artifact(task_id: str, kind: str) -> FileResponse:
        if not _TASK_ID_RE.fullmatch(task_id):
            raise HTTPException(status_code=404, detail="artifact not found")
        value = record(task_id)
        if value.execution is None:
            raise HTTPException(status_code=404, detail="artifact not found")
        names = {
            "before": ("working_copy_before.png", "image/png", False),
            "after": ("working_copy_after.png", "image/png", False),
            "diff": ("working_copy_diff.png", "image/png", False),
            "png": ("working_copy_after.png", "image/png", True),
            "pdf": ("working_copy.pdf", "application/pdf", True),
            "cdr": ("working_copy.cdr", "application/octet-stream", True),
        }
        selected = names.get(kind)
        if selected is None:
            raise HTTPException(status_code=404, detail="artifact not found")
        filename, media_type, download = selected
        path = (approved_workspace / "runs" / task_id / filename).resolve(strict=False)
        try:
            path.relative_to(approved_workspace)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="artifact not found") from exc
        if not path.is_file():
            raise HTTPException(status_code=404, detail="artifact not found")
        return FileResponse(
            path,
            media_type=media_type,
            filename=filename if download else None,
            headers={"Cache-Control": "no-store"},
        )

    return app


def _execution_summary(record: _PlanRecord) -> dict[str, Any]:
    execution = record.execution or {}
    visual = execution.get("visual_qa") or execution.get("metadata", {}).get("visual_qa_v2") or {}
    return {
        "task_id": record.task_id,
        "status": execution.get("result", "FAILED"),
        "operation_count": execution.get("operation_count", 0),
        "source_unchanged": execution.get("source_unchanged", False),
        "transaction_committed": execution.get("transaction_committed", False),
        "rollback_verified": execution.get("rollback_verified", False),
        "editability_verified": execution.get("editability_verified", False),
        "save_completed": execution.get("metadata", {}).get("save_completed", False),
        "reopen_completed": execution.get("metadata", {}).get("reopen_completed", False),
        "qa": {
            "status": visual.get("status", "FAILED"),
            "reasons": visual.get("reasons", visual.get("issues", [])),
        },
        "artifacts": {
            name: f"/api/v1/corel-ui/artifact/{record.task_id}/{name}"
            for name in ("before", "after", "diff", "cdr", "pdf", "png")
        },
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
.source-lock{padding:10px;border:1px solid #2f6552;background:#172b25;border-radius:8px;color:#9ae1bd;font-weight:700}.working{margin-top:8px;color:var(--muted)}
.stats{display:grid;grid-template-columns:1fr 1fr;gap:8px}.stat{background:var(--panel2);border-radius:8px;padding:10px}.stat b{display:block;font-size:19px}.stat span{color:var(--muted);font-size:11px}
.top-grid{display:grid;grid-template-columns:1.05fr .95fr;gap:16px}.plan{min-height:260px}.empty{color:var(--muted);display:grid;place-items:center;min-height:120px;text-align:center}.badge{display:inline-flex;padding:5px 8px;border-radius:999px;background:#30383d;font-size:11px;font-weight:800}.badge.pass{background:#17462e;color:#9ae1bd}.badge.review{background:#513f19;color:#f6d889}.badge.fail{background:#512626;color:#ffaaaa}
.plan-row{display:grid;grid-template-columns:110px 1fr;gap:9px;padding:8px 0;border-bottom:1px solid var(--line)}.plan-row span:first-child{color:var(--muted)}.command-log{margin-top:12px;padding-top:12px;border-top:1px solid var(--line);color:var(--muted);max-height:88px;overflow:auto}
.qa{display:grid;grid-template-columns:180px 1fr;gap:14px;align-items:center}.qa-status{font-size:25px;font-weight:900}.preview-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}.preview{background:#0d1011;border:1px solid var(--line);border-radius:9px;overflow:hidden}.preview h3{font-size:12px;padding:9px 11px;color:var(--muted)}.preview-frame{height:48vh;min-height:300px;background:#d9dcda;display:grid;place-items:center}.preview img{max-width:100%;max-height:100%;object-fit:contain}.outputs{display:flex;gap:9px;flex-wrap:wrap}.agent-message{padding:10px 12px;border-left:3px solid var(--cyan);background:#142326;color:#cbe7e4;border-radius:0 8px 8px 0;margin-top:10px}details{margin-top:12px;color:var(--muted)}pre{white-space:pre-wrap;word-break:break-word;background:#0d1113;padding:10px;border-radius:7px;font-size:11px}
@media(max-width:1050px){.shell{grid-template-columns:1fr}.top-grid{grid-template-columns:1fr}.preview-grid{grid-template-columns:1fr}.preview-frame{height:55vh}}
</style></head><body>
<header><strong>COREL CODEX · SAFE OPERATOR</strong><div class="safe">● LOCAL ONLY · SOURCE READ ONLY</div></header>
<main class="shell"><aside class="sidebar">
<section class="panel"><h2>Document</h2><div class="source-lock">SOURCE FILE: READ ONLY</div><div class="working" id="working">WORKING COPY: chưa tạo</div><div class="field" style="margin-top:14px"><label>Safe inventory/document ID</label><input id="fileId" placeholder="file:…" value="file:2af26b5496e33f1a4e00f2360ccc7909"></div><button id="inspect" class="primary">Inspect document</button><div id="documentMeta" class="empty">Chưa inspect document</div></section>
<section class="panel"><h2>Execution controls</h2><div class="actions"><button id="approve" class="primary" disabled>Approve</button><button id="cancel" disabled>Cancel</button><button id="rollback" class="danger" disabled>Undo / Rollback</button></div><p class="working">Mutation chỉ chạy sau khi bạn bấm Approve. Failure tự rollback trong transaction.</p></section>
<section class="panel"><h2>Outputs</h2><div id="outputs" class="outputs"><span class="empty">Chưa có output</span></div></section>
</aside><section class="workspace">
<div class="top-grid"><section class="panel"><h2>Chat / command</h2><div class="field"><label>Yêu cầu tiếng Việt</label><textarea id="instruction" placeholder="Ví dụ: Đổi nội dung của object…"></textarea></div><button id="planButton" class="primary" disabled>Ask Codex to plan</button><div id="agentMessage" class="agent-message">Inspect document trước khi lập plan.</div><div id="recent" class="command-log">Recent commands: —</div></section>
<section class="panel plan"><h2>Plan preview</h2><div id="planPanel" class="empty">Plan sẽ hiển thị ở đây trước execution.</div><details><summary>Debug details</summary><pre id="debug">—</pre></details></section></div>
<section class="panel"><h2>Visual QA</h2><div class="qa"><div id="qaStatus" class="qa-status">WAITING</div><div id="qaReason" class="working">Chưa có execution.</div></div></section>
<section class="panel"><h2>Before / After / Diff</h2><div class="preview-grid"><article class="preview"><h3>BEFORE</h3><div class="preview-frame"><img id="before" alt="Before preview"></div></article><article class="preview"><h3>AFTER</h3><div class="preview-frame"><img id="after" alt="After preview"></div></article><article class="preview"><h3>DIFF</h3><div class="preview-frame"><img id="diff" alt="Diff preview"></div></article></div></section>
</section></main><script>
const $=id=>document.getElementById(id);let currentTask=null,currentPlan=null,recent=[];const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function api(path,options={}){const response=await fetch(path,{headers:{'Content-Type':'application/json'},...options});const data=await response.json().catch(()=>({detail:response.statusText}));if(!response.ok)throw new Error(data.detail||response.statusText);return data}
function busy(message){$('agentMessage').textContent=message}function showError(error){busy(error.message);$('qaStatus').textContent='FAILED';$('qaStatus').className='qa-status';$('qaReason').textContent=error.message}
$('inspect').onclick=async()=>{try{busy('Đang inspect Corel document ở chế độ read-only…');const d=await api('/api/v1/corel-ui/document',{method:'POST',body:JSON.stringify({file_id:$('fileId').value.trim()})});$('documentMeta').className='stats';$('documentMeta').innerHTML=`<div class="stat"><b>${d.page_count}</b><span>pages</span></div><div class="stat"><b>${d.object_count}</b><span>objects</span></div><div class="stat"><b>${d.text_object_count}</b><span>editable text</span></div><div class="stat"><b>${d.vector_count}</b><span>vectors</span></div>`;$('planButton').disabled=false;busy(`Inspection PASS · ${d.corel_version}`)}catch(e){showError(e)}};
$('planButton').onclick=async()=>{const instruction=$('instruction').value.trim();if(!instruction)return;try{$('planButton').disabled=true;busy('Codex đang inspect qua MCP và lập bounded plan…');const p=await api('/api/v1/corel-ui/plan',{method:'POST',body:JSON.stringify({file_id:$('fileId').value.trim(),instruction})});currentTask=p.task_id;currentPlan=p;recent.unshift(instruction);$('recent').textContent='Recent commands: '+recent.slice(0,4).join(' · ');renderPlan(p)}catch(e){showError(e)}finally{$('planButton').disabled=false}};
function renderPlan(p){const badge=p.status==='PLANNED'?'pass':p.status==='NEEDS_REVIEW'?'review':'fail';$('planPanel').className='';$('planPanel').innerHTML=`<div class="actions"><span class="badge ${badge}">${esc(p.status)}</span><span class="badge">RISK ${esc(p.risk)}</span></div>${p.actions.length?p.actions.map(a=>`<div class="plan-row"><span>${esc(a.operation)}</span><div><b>${esc(a.target)}</b><br><span class="working">${esc(JSON.stringify(a.value))}</span></div></div>`).join(''):'<div class="empty">Không có executable action.</div>'}`;$('debug').textContent=JSON.stringify(p,null,2);$('approve').disabled=!p.can_approve;$('cancel').disabled=false;$('rollback').disabled=false;busy(p.message+(p.can_approve?' · Chờ bạn Approve.':' · Mutation bị giữ lại.'));$('qaStatus').textContent=p.status;$('qaStatus').className='qa-status';$('qaReason').textContent=p.policy_errors?.join(', ')||'Plan-only; chưa mutation.'}
$('approve').onclick=async()=>{if(!currentTask)return;try{$('approve').disabled=true;busy('Đã Approve. Operator đang tạo working copy, transaction, QA và save/reopen…');const x=await api('/api/v1/corel-ui/approve',{method:'POST',body:JSON.stringify({task_id:currentTask,approved:true})});renderExecution(x)}catch(e){showError(e)}};
function renderExecution(x){$('working').textContent=`WORKING COPY: ${x.status} · editable=${x.editability_verified}`;$('qaStatus').textContent=x.qa.status;$('qaStatus').className='qa-status '+(x.qa.status==='PASS'?'pass':x.qa.status==='NEEDS_REVIEW'?'review':'fail');$('qaReason').textContent=x.qa.reasons?.join(', ')||'Không có reason code.';['before','after','diff'].forEach(k=>$(k).src=x.artifacts[k]+'?v='+Date.now());$('outputs').innerHTML=['cdr','pdf','png'].map(k=>`<a class="button" href="${x.artifacts[k]}">Download ${k.toUpperCase()}</a>`).join('');$('rollback').disabled=false;busy(`${x.status} · save=${x.save_completed} · reopen=${x.reopen_completed} · source unchanged=${x.source_unchanged}`);$('debug').textContent=JSON.stringify(x,null,2)}
$('cancel').onclick=async()=>{if(!currentTask)return;try{const x=await api('/api/v1/corel-ui/cancel',{method:'POST',body:JSON.stringify({task_id:currentTask})});busy(x.status);$('approve').disabled=true;$('cancel').disabled=true}catch(e){showError(e)}};
$('rollback').onclick=async()=>{if(!currentTask)return;try{const x=await api('/api/v1/corel-ui/rollback',{method:'POST',body:JSON.stringify({task_id:currentTask})});busy(x.message||x.status);$('debug').textContent=JSON.stringify(x,null,2)}catch(e){showError(e)}};
</script></body></html>"""


__all__ = [
    "CodexCliPlanBroker",
    "CodexPlannerUnavailable",
    "CodexPlanningResultV1",
    "PlanBroker",
    "create_corel_codex_ui_app",
]
