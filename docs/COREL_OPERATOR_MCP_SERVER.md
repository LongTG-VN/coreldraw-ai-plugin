# CorelDRAW Safe Operator MCP Server

## Status

The local MCP adapter is implemented on top of the existing typed operator service. It does not expose raw Corel COM, VBA, Python, shell execution, or arbitrary filesystem paths.

The server uses the official Python MCP SDK v1 line (`mcp>=1.27,<2`). The default transport is `stdio`; optional Streamable HTTP binds only to loopback.

Primary SDK reference: <https://github.com/modelcontextprotocol/python-sdk>

## Safety boundary

```text
MCP client
  -> opaque inventory file ID
  -> inspect / deterministic plan
  -> explicit execution confirmation
  -> MutationPlanV1 validation
  -> serialized Corel owner
  -> Corel-created working copy
  -> transaction + postconditions
  -> editable reopen + visual integrity QA
```

- Source CDR/CDT files are read-only and are never saved.
- Mutations write only to a new `runs/<task_id>/working_copy.cdr` under the configured workspace.
- A task ID cannot be reused to overwrite output.
- Corel access is serialized by one re-entrant process lock.
- File access uses only `file:<32 lowercase hex>` inventory IDs.
- Text is hidden by default when listing objects.
- Every mutation defaults to plan-only and requires `execution_confirmed=true`.
- Visual QA checks deterministic integrity signals; it is not an aesthetic judge.

## Start with stdio

```powershell
python -m training.tools.corel_operator_mcp_server `
  --archive-root "<COMPANY_ARCHIVE_ROOT>" `
  --inventory "training/workspace/company_archive/archive.sqlite" `
  --workspace "training/workspace/company_archive/operator_mcp" `
  --transport stdio
```

## Start with local Streamable HTTP

```powershell
python -m training.tools.corel_operator_mcp_server `
  --archive-root "<COMPANY_ARCHIVE_ROOT>" `
  --inventory "training/workspace/company_archive/archive.sqlite" `
  --workspace "training/workspace/company_archive/operator_mcp" `
  --transport streamable-http `
  --host 127.0.0.1 `
  --port 8012
```

Non-loopback hosts fail at startup. The Streamable HTTP MCP endpoint is `/mcp` as provided by FastMCP.

## Tools

| Tool | Mutation | Purpose |
|---|---:|---|
| `corel_get_document` | no | Inspect one inventory CDR and return sanitized document/capability counts. |
| `corel_list_objects` | no | List stable inspector IDs, geometry, types, and optionally text. |
| `corel_find_text` | no | Find literal or bounded-regex text in one document. |
| `corel_plan_task` | no | Parse one explicit instruction into a strict plan. |
| `corel_run_task` | optional | Inspect, plan, optionally execute, reopen, and visual-QA one task. |
| `corel_execute_plan` | yes | Execute an already-validated plan after explicit confirmation. |
| `corel_visual_qa` | no | Compare an existing task's before/after previews. |

## Controlled instruction grammar

The current planner is deterministic and reports `planner_is_ai=false`. It accepts a deliberately small grammar:

```text
Đổi "old text" thành "new text"
Số điện thoại thành 0900 000 000
Giá thành 99K
Cỡ chữ object_7 thành 24
Di chuyển object_7 đến x=10, y=20
Đổi kích thước object_7 thành width=40, height=15
Tăng object_7 5%
```

Business values must be explicit in the instruction. Ambiguous targets, unsupported language, more than ten actions, out-of-bound values, or mismatched object types fail closed.

## Production-style CLI smoke

Plan only:

```powershell
python -m training.tools.run_corel_operator_task `
  --archive-root "<COMPANY_ARCHIVE_ROOT>" `
  --inventory "training/workspace/company_archive/archive.sqlite" `
  --workspace "training/workspace/company_archive/operator_tasks" `
  --file-id "file:<OPAQUE_ID>" `
  --task-id "price-change-review" `
  --instruction "Giá thành 99K"
```

Execute only after reviewing the returned plan:

```powershell
python -m training.tools.run_corel_operator_task `
  --archive-root "<COMPANY_ARCHIVE_ROOT>" `
  --inventory "training/workspace/company_archive/archive.sqlite" `
  --workspace "training/workspace/company_archive/operator_tasks" `
  --file-id "file:<OPAQUE_ID>" `
  --task-id "price-change-approved" `
  --instruction "Giá thành 99K" `
  --execute
```

Use a new task ID for every execution. Output paths returned by the service are workspace-relative.

## Known limits

- This is a safe bounded operator, not a general natural-language design agent.
- Active-page object addressing is stronger than multi-page addressing.
- Current real scale evidence is dominated by small font-size changes.
- Corel PNG export can change raster dimensions after a bounded edit; those cases are held as `NEEDS_REVIEW`.
- A PASS means technical visual integrity, not improved aesthetics.
