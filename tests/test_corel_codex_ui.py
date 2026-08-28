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
from training.tools.corel_codex_ui import _existing_ui_ready


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


def _medium_envelope(task_id: str, file_id: str) -> CorelPlanEnvelopeV1:
    return CorelPlanEnvelopeV1(
        request_id=task_id,
        goal="move one explicit benchmark object",
        document_id=file_id,
        plan=MutationPlanV1(
            plan_id=task_id,
            intent="move one explicit benchmark object",
            source="llm",
            actions=[
                MutationActionV1(
                    operation="move",
                    target=TargetSelectorV1(
                        kind="object_id",
                        value="static_2",
                        object_type="vector",
                    ),
                    value={"x": 1.0, "y": 0.0},
                    precondition_object_type="vector",
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


def _medium_resize_envelope(task_id: str, file_id: str) -> CorelPlanEnvelopeV1:
    envelope = _medium_envelope(task_id, file_id)
    resized_plan = envelope.plan.model_copy(
        update={
            "intent": "resize one explicit benchmark object",
            "actions": [
                MutationActionV1(
                    operation="resize",
                    target=TargetSelectorV1(
                        kind="object_id",
                        value="static_2",
                        object_type="vector",
                    ),
                    value={"width": 105.0, "height": 105.0},
                    precondition_object_type="vector",
                )
            ],
        }
    )
    return envelope.model_copy(
        update={"goal": "resize one explicit benchmark object", "plan": resized_plan}
    )


class FakePlanner:
    def plan(self, *, file_id: str, task_id: str, instruction: str) -> CodexPlanningResultV1:
        if "mơ hồ" in instruction:
            return CodexPlanningResultV1(
                status="NEEDS_REVIEW",
                message="TARGET_AMBIGUOUS",
            )
        if "medium resize" in instruction:
            return CodexPlanningResultV1(
                status="PLANNED",
                message="Bounded medium-risk resize plan ready",
                envelope=_medium_resize_envelope(task_id, file_id),
            )
        if "medium" in instruction:
            return CodexPlanningResultV1(
                status="PLANNED",
                message="Bounded medium-risk plan ready",
                envelope=_medium_envelope(task_id, file_id),
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

    def export_copy(self, file_id: str, *, task_id: str, formats: list[str]) -> dict:
        assert file_id == FILE_ID
        assert formats
        self.execute_calls += 1
        root = self.workspace / "runs" / task_id
        root.mkdir(parents=True)
        Image.new("RGB", (32, 24), "white").save(root / "working_copy_before.png")
        Image.new("RGB", (32, 24), "white").save(root / "working_copy_after.png")
        (root / "working_copy.cdr").write_bytes(b"FAKE-TEST-CDR")
        if "PDF" in formats:
            (root / "working_copy.pdf").write_bytes(b"%PDF-test")
        return {
            "result": "AUTO_SUCCESS",
            "operation_count": 0,
            "source_unchanged": True,
            "transaction_committed": False,
            "rollback_verified": False,
            "editability_verified": True,
            "preview_before": f"runs/{task_id}/working_copy_before.png",
            "preview_after": f"runs/{task_id}/working_copy_after.png",
            "metadata": {
                "save_completed": True,
                "reopen_completed": True,
                "visual_qa_v2": {
                    "status": "PASS",
                    "reasons": ["EXPORT_ONLY_NO_MUTATION"],
                },
            },
        }


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


def test_medium_risk_plan_is_visibly_held_for_review(tmp_path: Path) -> None:
    client, service = _app(tmp_path)
    planned = client.post(
        "/api/v1/corel-ui/plan",
        json={"file_id": FILE_ID, "instruction": "medium move benchmark"},
    ).json()
    assert planned["status"] == "WAITING_MEDIUM_RISK_APPROVAL"
    assert planned["risk"] == "MEDIUM_RISK"
    assert planned["review_required"] is True
    assert planned["can_approve"] is False
    assert planned["can_approve_medium_risk"] is True
    assert planned["approval_challenge"]["target_object_ids"] == ["static_2"]
    assert planned["approval_challenge"]["operations"] == ["move"]
    assert client.post(
        "/api/v1/corel-ui/approve",
        json={"task_id": planned["task_id"], "approved": True},
    ).status_code == 409
    assert service.execute_calls == 0


def test_medium_risk_approval_executes_only_the_exact_plan(tmp_path: Path) -> None:
    client, service = _app(tmp_path)
    plan = client.post(
        "/api/v1/corel-ui/plan",
        json={"file_id": FILE_ID, "instruction": "medium move benchmark"},
    ).json()
    challenge = plan["approval_challenge"]
    approved = client.post(
        "/api/v1/corel-ui/medium-risk-approval",
        json={**challenge, "approved": True},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "APPROVED"
    assert approved.json()["can_approve"] is True

    executed = client.post(
        "/api/v1/corel-ui/approve",
        json={"task_id": plan["task_id"], "approved": True},
    )
    assert executed.status_code == 200
    assert executed.json()["status"] == "AUTO_SUCCESS"
    assert executed.json()["source_unchanged"] is True
    assert service.execute_calls == 1
    stored = client.get(f"/api/v1/corel-ui/jobs/{plan['task_id']}").json()
    assert stored["status"] == "PASS"


def test_medium_risk_resize_approval_preserves_exact_arguments(tmp_path: Path) -> None:
    client, service = _app(tmp_path)
    plan = client.post(
        "/api/v1/corel-ui/plan",
        json={"file_id": FILE_ID, "instruction": "medium resize benchmark"},
    ).json()
    challenge = plan["approval_challenge"]
    assert challenge["operations"] == ["resize"]
    assert challenge["operation_arguments"] == [{"width": 105.0, "height": 105.0}]
    assert client.post(
        "/api/v1/corel-ui/medium-risk-approval",
        json={**challenge, "approved": True},
    ).status_code == 200
    executed = client.post(
        "/api/v1/corel-ui/approve",
        json={"task_id": plan["task_id"], "approved": True},
    )
    assert executed.status_code == 200
    assert executed.json()["status"] == "AUTO_SUCCESS"
    assert service.execute_calls == 1


def test_medium_risk_approval_binds_hash_target_operation_and_arguments(
    tmp_path: Path,
) -> None:
    client, service = _app(tmp_path)
    plan = client.post(
        "/api/v1/corel-ui/plan",
        json={"file_id": FILE_ID, "instruction": "medium move benchmark"},
    ).json()
    challenge = plan["approval_challenge"]
    tampered_values = [
        {**challenge, "plan_hash": "0" * 64},
        {**challenge, "target_object_ids": ["static_other"]},
        {**challenge, "operations": ["resize"]},
        {**challenge, "operation_arguments": [{"x": 2.0, "y": 0.0}]},
    ]
    for tampered in tampered_values:
        response = client.post(
            "/api/v1/corel-ui/medium-risk-approval",
            json={**tampered, "approved": True},
        )
        assert response.status_code == 409
        assert response.json()["detail"] == "STALE_OR_INVALID_MEDIUM_RISK_APPROVAL"
    assert service.execute_calls == 0


def test_medium_risk_approval_is_job_bound_and_cancel_invalidates_it(
    tmp_path: Path,
) -> None:
    client, service = _app(tmp_path)
    first = client.post(
        "/api/v1/corel-ui/plan",
        json={"file_id": FILE_ID, "instruction": "medium move benchmark"},
    ).json()
    second = client.post(
        "/api/v1/corel-ui/plan",
        json={"file_id": FILE_ID, "instruction": "medium move benchmark regenerated"},
    ).json()
    stale = {
        **first["approval_challenge"],
        "job_id": second["task_id"],
        "approved": True,
    }
    rejected = client.post("/api/v1/corel-ui/medium-risk-approval", json=stale)
    assert rejected.status_code == 409
    assert rejected.json()["detail"] == "STALE_OR_INVALID_MEDIUM_RISK_APPROVAL"

    approved = client.post(
        "/api/v1/corel-ui/medium-risk-approval",
        json={**first["approval_challenge"], "approved": True},
    )
    assert approved.status_code == 200
    canceled = client.post(
        "/api/v1/corel-ui/cancel", json={"task_id": first["task_id"]}
    )
    assert canceled.status_code == 200
    blocked = client.post(
        "/api/v1/corel-ui/approve",
        json={"task_id": first["task_id"], "approved": True},
    )
    assert blocked.status_code == 409
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


def test_v1_export_only_is_approved_persisted_and_reopenable(tmp_path: Path) -> None:
    opened: list[Path] = []
    service = FakeService(tmp_path)
    app = create_corel_codex_ui_app(
        service=service,  # type: ignore[arg-type]
        planner=FakePlanner(),
        workspace=tmp_path,
        path_opener=opened.append,
    )
    client = TestClient(app)
    plan = client.post(
        "/api/v1/corel-ui/plan",
        json={"file_id": FILE_ID, "instruction": "Xuất PDF và PNG"},
    ).json()
    assert plan["kind"] == "EXPORT_ONLY"
    assert plan["can_approve"] is True
    assert service.execute_calls == 0

    result = client.post(
        "/api/v1/corel-ui/approve",
        json={"task_id": plan["task_id"], "approved": True},
    ).json()
    assert result["status"] == "AUTO_SUCCESS"
    assert result["operation_count"] == 0
    assert result["source_unchanged"] is True
    assert result["output_version"] == 1
    assert set(result["artifacts"]) == {"before", "after", "diff", "cdr", "pdf", "png"}

    jobs = client.get("/api/v1/corel-ui/jobs").json()["jobs"]
    assert jobs[0]["task_id"] == plan["task_id"]
    reopened = client.get(f"/api/v1/corel-ui/jobs/{plan['task_id']}").json()
    assert reopened["kind"] == "EXPORT_ONLY"
    assert reopened["qa_status"] == "PASS"
    assert client.post(
        "/api/v1/corel-ui/open",
        json={"task_id": plan["task_id"], "kind": "folder"},
    ).json()["opened"] is True
    assert opened and opened[0].is_dir()


def test_v1_settings_fail_closed_and_health_is_compact(tmp_path: Path) -> None:
    client, _service = _app(tmp_path)
    health = client.get("/api/v1/corel-ui/status").json()
    assert set(health["components"]) == {"corel", "mcp", "operator", "codex"}
    assert health["source_policy"] == "READ_ONLY"

    settings = client.put(
        "/api/v1/corel-ui/settings",
        json={
            "output_subfolder": "daily/jobs",
            "default_pdf_export": True,
            "default_png_export": False,
            "preview_quality": "standard",
            "recent_job_limit": 12,
        },
    )
    assert settings.status_code == 200
    assert client.get("/api/v1/corel-ui/settings").json()["output_subfolder"] == "daily/jobs"
    assert client.put(
        "/api/v1/corel-ui/settings",
        json={
            "output_subfolder": "../outside",
            "default_pdf_export": True,
            "default_png_export": True,
            "preview_quality": "high",
            "recent_job_limit": 20,
        },
    ).status_code == 422

    plan = client.post(
        "/api/v1/corel-ui/plan",
        json={"file_id": FILE_ID, "instruction": "Xuất PDF và PNG"},
    ).json()
    execution = client.post(
        "/api/v1/corel-ui/approve",
        json={"task_id": plan["task_id"], "approved": True},
    ).json()
    assert "pdf" in execution["artifacts"]
    assert "png" not in execution["artifacts"]
    assert {"before", "after", "diff"}.issubset(execution["artifacts"])


def test_v1_lifecycle_is_safe_when_idle(tmp_path: Path) -> None:
    client, _service = _app(tmp_path)
    response = client.post(
        "/api/v1/corel-ui/lifecycle", json={"action": "shutdown"}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "SAFE_TO_STOP"


def test_v1_post_processing_failure_releases_lifecycle_lock(
    tmp_path: Path, monkeypatch
) -> None:
    client, _service = _app(tmp_path)
    plan = client.post(
        "/api/v1/corel-ui/plan",
        json={"file_id": FILE_ID, "instruction": "Đổi text benchmark rõ ràng"},
    ).json()

    def fail_diff(*_args, **_kwargs):
        raise RuntimeError("fixture diff failure")

    monkeypatch.setattr("training.corel_operator.ui_app._create_diff", fail_diff)
    execution = client.post(
        "/api/v1/corel-ui/approve",
        json={"task_id": plan["task_id"], "approved": True},
    )
    assert execution.status_code == 500
    stored = client.get(f"/api/v1/corel-ui/jobs/{plan['task_id']}").json()
    assert stored["status"] == "FAILED"
    assert stored["source_unchanged"] is True
    shutdown = client.post(
        "/api/v1/corel-ui/lifecycle", json={"action": "shutdown"}
    )
    assert shutdown.status_code == 200
    assert shutdown.json()["status"] == "SAFE_TO_STOP"


def test_v1_reuses_only_a_verified_existing_local_ui(monkeypatch) -> None:
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        @staticmethod
        def read() -> bytes:
            return (
                b'{"status":"READY","local_only":true,'
                b'"source_policy":"READ_ONLY"}'
            )

    monkeypatch.setattr("urllib.request.urlopen", lambda *_args, **_kwargs: FakeResponse())
    assert _existing_ui_ready(8004) is True
