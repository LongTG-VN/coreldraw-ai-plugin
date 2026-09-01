# Canonical Execution Path

## Product path

The supported daily-use path is:

```text
start_corel_ai.bat
  -> training.tools.corel_codex_ui
  -> loopback Corel UI/API (127.0.0.1:8004)
  -> CodexCliPlanBroker (structured planning only)
  -> strict CorelPlanEnvelopeV1 validation
  -> semantic policy and target resolution
  -> explicit low-risk or exact-bound medium-risk approval
  -> OperatorToolService (serialized Corel boundary)
  -> SafeCorelOperator
  -> fresh working copy
  -> CorelOperatorRuntime / transaction engine
  -> structural QA + page-anchored Visual Integrity QA
  -> save, close, reopen, editability check
  -> versioned local CDR/PDF/PNG + before/after/diff
```

The planner never receives COM, VBA, shell, arbitrary-path, save, or overwrite
authority. Its output is untrusted data. `OperatorToolService` accepts opaque
inventory IDs, resolves the source inside the approved archive, and serializes
Corel access with one re-entrant lock.

## Mandatory invariants

1. Source CDR/CDT is read-only and guarded before/after execution.
2. Every mutation targets a fresh workspace CDR copy.
3. Schema, semantic policy, and unique target resolution run before mutation.
4. Geometry/typography operations require a job-bound exact-plan approval.
5. Related operations execute in one Corel command-group transaction.
6. Failed transactions roll back or fail closed; uncertain output is rejected.
7. Accepted output must pass structural scope checks, Visual Integrity QA,
   save/reopen, and editability verification.
8. Paths returned to the UI are workspace-relative and artifact reads cannot
   escape the approved workspace.

## Supported entry points

- **Canonical UI:** `python -m training.tools.corel_codex_ui`.
- **Bounded MCP:** `training.corel_operator.mcp_server`, eight loopback-only
  tools. It exposes inspect/context/object/text/plan/run/execute/QA, requires
  explicit confirmation for mutation, and delegates to the same tool service.
- **Design API:** `main.py` provides lower-level `/api/v1/design/*` and legacy
  `/api/v1/corel/*` capabilities for controlled integration and maintenance.
  It is not the supervised product workflow and must not be used to bypass the
  operator policy or approval contract.
- **Deterministic operator agent:** retained for hermetic tests, dry-runs, and
  controlled non-AI regression workflows.

## Research-only or inactive paths

Training, preference collection, Gold grammar, visual RAG, and vision critic
packages are research surfaces. Visual RAG v0.3.4 and Vision Critic v0.3.5 are
preserved failed experiments and are not enabled by default. The optional
OpenAI planner adapter is plan-only and currently not configured on this host.

## Startup and shutdown

`start_corel_ai.bat` checks Python and inventory, then the Python launcher
checks Corel, MCP registration, operator workspace, Codex login, and port 8004.
It neither edits registry/global configuration nor starts a second server on an
already healthy port. Shutdown/restart is refused while a job owns a
transaction; `Ctrl+C` performs Uvicorn application shutdown when idle.
