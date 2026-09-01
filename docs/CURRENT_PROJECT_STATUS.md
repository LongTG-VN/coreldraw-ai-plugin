# Current Project Status

Status date: 2026-09-01.

## Stable product capability

- Local Windows/CorelDRAW operator UI and loopback MCP transport.
- Read-only inventory identifiers and serialized Corel COM ownership.
- Strict plan schemas, fail-closed policy, unique target resolution.
- Explicit confirmation; exact-plan binding for medium-risk MOVE/RESIZE.
- Working-copy-only transaction, rollback, structural and visual integrity QA.
- Editable CDR output plus versioned PNG/PDF and before/after/diff artifacts.
- Save, close/reopen, target persistence, and source-integrity verification.
- Local recent-job history, health, recovery guidance, and safe shutdown.

The post-merge host preflight reported READY for Corel, MCP, Operator, and
Codex. A bounded post-merge smoke verified read-only inspection, one low-risk
text replacement, and one explicitly approved medium-risk MOVE. Both mutations
were `AUTO_SUCCESS` with Visual QA PASS, save/reopen PASS, editable target PASS,
and zero source mutations.

## AI and research state

- Qwen3-1.7B remains the preserved local/offline fallback planner; no retraining
  is part of product stabilization.
- v0.3.3 Asset-Aware Composition is the last successful design-quality research
  checkpoint.
- v0.3.4 Visual RAG is a failed research experiment and disabled by default.
- v0.3.5 Vision Critic/Self-Refine is a failed research experiment and disabled
  by default.
- Human preference tooling exists, but preference training is not ready and no
  preference model is trained.
- The optional real-OpenAI planner adapter is plan-only, host-bound, and not
  configured on this machine. No real-provider claim is made.

## Production assessment

The supervised V1 workflow is suitable for bounded daily use with human review.
It is not a cloud service, an arbitrary autonomous designer, or commercially
cleared AI training pipeline. Real-company source data and generated working
artifacts remain local and ignored. Operator reliability evidence is strong for
bounded operations, but legacy/pasteboard-heavy CDRs and transient Corel COM
state can still require review or fail closed.

## Current limits

- Corel automation requires a running, compatible Windows desktop installation.
- The company inventory database and archive root are local prerequisites.
- Codex-host planning may send the bounded instruction/context requested by the
  user; customer text inclusion is opt-in and should be minimized.
- Post-commit undo of an output copy is not represented as source rollback; the
  completed versioned copy is preserved and a new job should be used.
- Visual QA checks integrity/change scope, not beauty or human preference.
