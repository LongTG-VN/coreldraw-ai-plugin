# Test Suite Map

At the post-merge baseline, pytest collected and passed 467 tests across 65
`test_*.py` files. Tests are hermetic unless explicitly run through a separate
real-Corel tool; CI does not require CorelDRAW, private archives, CUDA, Qwen,
external LLM credentials, or human review data.

## Product and safety groups

| Group | Principal files | Coverage |
| --- | --- | --- |
| Corel Operator (16 files) | `test_corel_operator*.py` | runtime adapters, transactions, target resolution, structural scope, rollback, artifacts, batch isolation/resume, reliability, Visual QA V2, real-evidence summarization |
| Agent/UI/provider (5 files) | `test_corel_agent.py`, `test_corel_codex_ui.py`, `test_corel_real_llm_provider.py`, final-gate tests | strict envelopes, Vietnamese boundaries, policy, exact-plan approval, UI lifecycle/history/health, optional provider fail-closed behavior |
| Company archive (5 files) | `test_company_archive.py`, review/pasteboard/manual/real-pilot tests | immutable scanning, inventory, previews, sanitized review packaging, curation and real-CDR contracts |
| Core Design API (4 files) | `test_plugin.py`, `test_design_bridge.py`, `test_document_io.py`, `test_transaction_engine.py` | API contracts, editable objects, I/O path validation, save/open/export, transaction rollback |
| Design/training research (35 files) | remaining `test_*.py` | schemas, RAG/retrieval, v0.3.x/v0.4 guards, assets, typography, release integrity, training bootstrap/inference |

## Critical regression contracts

- Source paths resolve only within approved roots; source files remain
  unchanged.
- MCP is loopback-only and exposes no shell, VBA, raw COM, or arbitrary paths.
- Mutation requires explicit confirmation; medium-risk approval binds job,
  plan hash, stable target IDs, operations, and exact arguments.
- Stale/tampered/canceled approval is rejected.
- Transaction failure rolls back; unrelated structural changes are rejected.
- Save/reopen and target editability are verified before success.
- Artifact reads and UI output subfolders cannot traverse outside workspace.
- Provider credentials are optional; unconfigured providers fail closed and
  injected fake clients cover strict structured plan behavior.
- Research experiments and human-preference provenance cannot silently become
  production/human evidence.

## Commands

```powershell
python -m compileall -q training tests
python -m pytest -q
git diff --check
```

CI additionally runs `python -m compileall -q .` in a clean checkout for Python
3.10, 3.11, and 3.12.
