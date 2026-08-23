from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from training.corel_agent.models import CorelPlanEnvelopeV1, PlannerProvenanceV1
from training.corel_operator.models import MutationActionV1, MutationPlanV1, TargetSelectorV1
from training.corel_operator.ui_app import (
    CodexCliPlanBroker,
    CodexPlanningResultV1,
    create_corel_codex_ui_app,
)


FILE_ID = "file:" + "a" * 32


def _envelope(task_id: str, file_id: str) -> CorelPlanEnvelopeV1:
    return CorelPlanEnvelopeV1(
        request_id=task_id,
        goal="replace one explicit benchmark text value",
        document_id=file_id,
        plan=MutationPlanV1(
            plan_id=task_id,
            intent="replace one explicit benchmark text value",
            source="llm",
            actions=[
                MutationActionV1(
                    operation="replace_text",
                    target=TargetSelectorV1(
                        kind="object_id",
                        value="static_1",
                        object_type="text",
                    ),
                    value="BENCHMARK",
                    precondition_object_type="text",
                )
            ],
            metadata={"benchmark_sample_data": True},
        ),
        confidence=0.97,
        provenance=PlannerProvenanceV1(
            planner_type="llm",
            planner_provider="codex-host",
            planner_model="codex",
            planner_is_ai=True,
        ),
    )


class FakePlanner:
    def plan(self, *, file_id: str, task_id: str, instruction: str) -> CodexPlanningResultV1:
        if "mơ hồ" in instruction:
            return CodexPlanningResultV1(
                status="NEEDS_REVIEW",
                message="TARGET_AMBIGUOUS",
            )
        return CodexPlanningResultV1(
            status="PLANNED",
            message="Bounded plan ready",
            envelope=_envelope(task_id, file_id),
        )


class FakeService:
    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace
        self.execute_calls = 0

    def get_document(self, file_id: str) -> dict:
        assert file_id == FILE_ID
        return {
            "page_count": 1,
            "object_count": 2,
            "text_object_count": 1,
            "bitmap_count": 0,
            "vector_count": 1,
            "group_count": 0,
            "corel_version": "fixture",
        }

    def execute_plan(self, file_id: str, *, task_id: str, plan) -> dict:
        assert file_id == FILE_ID
        assert plan.source == "llm"
        self.execute_calls += 1
        root = self.workspace / "runs" / task_id
        root.mkdir(parents=True)
        Image.new("RGB", (32, 24), "white").save(root / "working_copy_before.png")
        Image.new("RGB", (32, 24), "black").save(root / "working_copy_after.png")
        (root / "working_copy.cdr").write_bytes(b"FAKE-TEST-CDR")
        (root / "working_copy.pdf").write_bytes(b"%PDF-test")
        return {
            "result": "AUTO_SUCCESS",
            "operation_count": 1,
            "source_unchanged": True,
            "transaction_committed": True,
            "rollback_verified": False,
            "editability_verified": True,
            "preview_before": f"runs/{task_id}/working_copy_before.png",
            "preview_after": f"runs/{task_id}/working_copy_after.png",
            "metadata": {"save_completed": True, "reopen_completed": True},
        }

    def visual_qa(self, *, task_id: str) -> dict:
        return {"status": "PASS", "reasons": [], "task_id": task_id}


def _app(tmp_path: Path):
    service = FakeService(tmp_path)
    app = create_corel_codex_ui_app(
        service=service,  # type: ignore[arg-type]
        planner=FakePlanner(),
        workspace=tmp_path,
    )
    return TestClient(app), service


def test_ui_full_approval_flow_is_working_copy_only(tmp_path: Path) -> None:
    client, service = _app(tmp_path)
    page = client.get("/corel-ui")
    assert page.status_code == 200
    assert "SOURCE FILE: READ ONLY" in page.text

    document = client.post("/api/v1/corel-ui/document", json={"file_id": FILE_ID})
    assert document.status_code == 200
    assert document.json()["source_policy"] == "READ_ONLY"

    planned = client.post(
        "/api/v1/corel-ui/plan",
        json={"file_id": FILE_ID, "instruction": "Đổi text benchmark rõ ràng"},
    )
    assert planned.status_code == 200
    plan = planned.json()
    assert plan["status"] == "PLANNED"
    assert plan["can_approve"] is True
    assert plan["planner"]["planner_is_ai"] is True
    assert service.execute_calls == 0

    missing_confirmation = client.post(
        "/api/v1/corel-ui/approve",
        json={"task_id": plan["task_id"], "approved": False},
    )
    assert missing_confirmation.status_code == 422
    assert service.execute_calls == 0

    executed = client.post(
        "/api/v1/corel-ui/approve",
        json={"task_id": plan["task_id"], "approved": True},
    )
    assert executed.status_code == 200
    result = executed.json()
    assert result["status"] == "AUTO_SUCCESS"
    assert result["source_unchanged"] is True
    assert result["editability_verified"] is True
    assert result["qa"]["status"] == "PASS"
    assert service.execute_calls == 1
    for kind in ("before", "after", "diff", "cdr", "pdf", "png"):
        assert client.get(result["artifacts"][kind]).status_code == 200

    duplicate = client.post(
        "/api/v1/corel-ui/approve",
        json={"task_id": plan["task_id"], "approved": True},
    )
    assert duplicate.status_code == 409
    assert service.execute_calls == 1


def test_ambiguous_plan_cannot_be_approved(tmp_path: Path) -> None:
    client, service = _app(tmp_path)
    planned = client.post(
        "/api/v1/corel-ui/plan",
        json={"file_id": FILE_ID, "instruction": "yêu cầu mơ hồ"},
    ).json()
    assert planned["status"] == "NEEDS_REVIEW"
    assert planned["can_approve"] is False
    response = client.post(
        "/api/v1/corel-ui/approve",
        json={"task_id": planned["task_id"], "approved": True},
    )
    assert response.status_code == 409
    assert service.execute_calls == 0


def test_cancel_before_execution_and_post_commit_rollback_contract(tmp_path: Path) -> None:
    client, _service = _app(tmp_path)
    plan = client.post(
        "/api/v1/corel-ui/plan",
        json={"file_id": FILE_ID, "instruction": "Đổi text benchmark rõ ràng"},
    ).json()
    canceled = client.post(
        "/api/v1/corel-ui/cancel", json={"task_id": plan["task_id"]}
    )
    assert canceled.json()["status"] == "CANCELED"
    assert client.post(
        "/api/v1/corel-ui/approve",
        json={"task_id": plan["task_id"], "approved": True},
    ).status_code == 409


def test_artifact_route_has_fixed_kind_and_safe_task_id(tmp_path: Path) -> None:
    client, _service = _app(tmp_path)
    assert client.get("/api/v1/corel-ui/artifact/../cdr").status_code == 404
    assert client.get("/api/v1/corel-ui/artifact/not-a-task/source").status_code == 404
    assert client.post(
        "/api/v1/corel-ui/document", json={"file_id": "../../source.cdr"}
    ).status_code == 422


def test_codex_broker_prefilters_vague_request_without_process(tmp_path: Path) -> None:
    broker = CodexCliPlanBroker(
        repo_root=tmp_path,
        workspace=tmp_path / "workspace",
        executable="definitely-missing-codex",
    )
    result = broker.plan(
        file_id=FILE_ID,
        task_id="safe-task",
        instruction="làm cho đẹp",
    )
    assert result.status == "NEEDS_REVIEW"
    assert result.envelope is None


def test_codex_command_is_read_only_and_never_uses_shell(tmp_path: Path) -> None:
    broker = CodexCliPlanBroker(
        repo_root=tmp_path,
        workspace=tmp_path / "workspace",
        executable="codex",
    )
    command = broker._command(
        schema_path=tmp_path / "schema.json",
        output_path=tmp_path / "output.json",
    )
    assert command[command.index("-s") + 1] == "read-only"
    assert "--ephemeral" in command
    assert "danger-full-access" not in command
    assert "--dangerously-bypass-approvals-and-sandbox" not in command
    assert command[-1] == "-"
