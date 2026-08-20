"""Official MCP transport for the bounded Corel operator tool service."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from training.corel_operator.agent import AutonomousOperatorAgent, OperatorTaskRequestV1
from training.corel_operator.tools import OperatorToolService


def create_mcp_server(
    service: OperatorToolService,
    *,
    host: str = "127.0.0.1",
    port: int = 8012,
) -> FastMCP:
    """Create a local-only server; every mutation remains policy-gated."""

    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("Corel operator MCP must bind to a loopback host")
    mcp = FastMCP(
        "CorelDRAW Safe Operator",
        instructions=(
            "Use opaque inventory file IDs. Inspect before planning. Mutations require "
            "explicit execution confirmation and always create a new editable working copy. "
            "Raw COM, VBA, shell, source overwrite, and arbitrary paths are unavailable."
        ),
        host=host,
        port=port,
        json_response=True,
        stateless_http=True,
    )
    agent = AutonomousOperatorAgent(service)

    @mcp.tool()
    def corel_get_document(file_id: str) -> dict[str, Any]:
        """Inspect one inventory CDR read-only and return sanitized capabilities."""

        return service.get_document(file_id)

    @mcp.tool()
    def corel_list_objects(
        file_id: str,
        object_type: str | None = None,
        include_text: bool = False,
    ) -> dict[str, Any]:
        """List stable object IDs; customer text is hidden unless explicitly requested."""

        return service.list_objects(
            file_id,
            object_type=object_type,
            include_text=include_text,
        )

    @mcp.tool()
    def corel_find_text(
        file_id: str,
        query: str,
        case_sensitive: bool = True,
        regex: bool = False,
    ) -> dict[str, Any]:
        """Find text in one approved CDR without changing it."""

        return service.find_text(
            file_id,
            query=query,
            case_sensitive=case_sensitive,
            regex=regex,
        )

    @mcp.tool()
    def corel_plan_task(
        file_id: str,
        task_id: str,
        instruction: str,
    ) -> dict[str, Any]:
        """Build a bounded deterministic plan; never executes a mutation."""

        request = OperatorTaskRequestV1(
            file_id=file_id,
            task_id=task_id,
            instruction=instruction,
            execution_confirmed=False,
        )
        return agent.run(request).model_dump(mode="json")

    @mcp.tool()
    def corel_run_task(
        file_id: str,
        task_id: str,
        instruction: str,
        execution_confirmed: bool = False,
    ) -> dict[str, Any]:
        """Run the safe agent loop; defaults to plan-only until explicitly confirmed."""

        request = OperatorTaskRequestV1(
            file_id=file_id,
            task_id=task_id,
            instruction=instruction,
            execution_confirmed=execution_confirmed,
        )
        return agent.run(request).model_dump(mode="json")

    @mcp.tool()
    def corel_execute_plan(
        file_id: str,
        task_id: str,
        plan: dict[str, Any],
        execution_confirmed: bool = False,
    ) -> dict[str, Any]:
        """Execute one strict MutationPlanV1 only after explicit confirmation."""

        if not execution_confirmed:
            return {
                "file_id": file_id,
                "task_id": task_id,
                "result": "CONFIRMATION_REQUIRED",
                "executed": False,
            }
        return service.execute_plan(file_id, task_id=task_id, plan=plan)

    @mcp.tool()
    def corel_visual_qa(task_id: str) -> dict[str, Any]:
        """Check visual integrity of one generated task; not an aesthetic score."""

        return service.visual_qa(task_id=task_id)

    return mcp


__all__ = ["create_mcp_server"]
