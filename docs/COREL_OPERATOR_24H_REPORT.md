# CorelDRAW AI Operator — Engineering Run Report

## Result

`COREL_OPERATOR_PARTIAL_BUT_USABLE`

The operator safely opened, inspected, copied, reopened, and exported 198 of 200 deterministic real company CDR samples. It automatically completed bounded mutations on 20 unique real working copies with editable reopen and zero source mutations. The result is not ready for unattended arbitrary editing: target coverage and operation breadth remain limited, and 2 census timeouts plus 8 mutation failures remain valid negative evidence.

## Executive summary

CorelDRAW remains the document owner. The operator understands only the target and declared property scope, leaving unknown objects untouched. It uses validated structured plans, exact target resolution, Corel transactions, postcondition checks, rollback, working-copy-only save/reopen, and source-stat guards.

No Qwen, Antigravity, Visual RAG, vision critic, Gold Grammar, preference training, aesthetic filtering, or planner shootout ran in this mission.

## Git

- Branch: `codex/corel-operator-24h`
- Baseline: `3f52b739b49664ac9eea5aee0a34f878512429d0`
- Final SHA: recorded after the final verification commit
- Public company artifacts committed: none
- Private visual package commit: `53cdc567921621b11bd9f943cd34917a18aec72e`

## Baseline

The repository already contained real Corel integration, transaction/rollback infrastructure, source archive inventory, preview/export paths, and editable CDR save/reopen evidence. It did not yet have a coherent fail-closed operator policy, deterministic coverage census, hard process isolation, resumable mutation pilot, stable unnamed-object targeting, or private before/after package.

## Architecture decision

The mission explicitly rejects full CDR reconstruction as a prerequisite for safe editing:

```text
intent -> MutationPlanV1 -> policy + exact target resolution
-> Corel-created working copy -> transaction -> validation
-> commit/Undo -> save/reopen editable CDR -> export -> audit
```

Corel preserves unsupported and unknown objects. Models cannot call raw COM, VBA, shell, or arbitrary methods.

## Operator coverage census

- Deterministic real sample: 200 files across five inventory file-size strata
- Corel open: 198/200 (99.0%)
- Inspection/object/text/bitmap/vector/group/page/pasteboard enumeration: 198/200 (99.0%) each
- Snapshot: 198/200 (99.0%)
- Save-as-copy and editable reopen: 198/200 (99.0%)
- PNG and PDF export: 198/200 (99.0%) each
- Safe close accounting: 200/200 (100%)
- Operator eligible: 198/200 (99.0%)
- Source mutations: 0

Median completed-file latency was 15.440 seconds; p95 was 55.958 seconds; mean was 24.714 seconds.

## Failure Pareto

Five files timed out initially. One explicit bounded retry wave recovered three; two remained timed out after 300 seconds. Final sample impact is 1.0%, classified medium by the mission threshold. No failures were removed or replaced.

## Coverage fixes

- hard subprocess isolation per real Corel file;
- resumable SQLite state and explicit failure retry;
- exact source and working-copy stat/path guards;
- bounded recovery that never saves the source and never kills CorelDRAW;
- stable operator object IDs for unnamed live Corel shapes;
- sanitized tokens/errors for public reporting;
- explicit persistence of unsupported and failed outcomes.

## Safe operator API

`training.corel_operator` provides strict models, source/workspace policy, target resolution, runtime adapter, transaction-aware service, batch/census state, mutation pilot, inspection helpers, deterministic fixture planning, bounded refinement, rollback verification, and sanitized artifact generation.

Enabled mutation-plan operations are text replacement, absolute move, absolute resize, rotation, font-family change, and font-size change. Create/delete/group/align/distribute remain outside the operator plan until their preservation rules pass real-company tests.

## Transaction / rollback

All actions in a plan execute within a Corel command group. The service verifies object count, object identity, non-target tracked properties, and the allowed property set for each target. Any failure calls Undo and checks snapshot restoration.

A real intentional-failure smoke verified rollback: transaction rollback reported true, the before snapshot returned, object count stayed 15, and the source stayed unchanged.

## 20-file mutation pilot

Primary pilot:

- files attempted: 20;
- automatic successes: 12;
- success with warning: 0;
- needs review: 0;
- unsupported: 3;
- failed: 5;
- source mutations: 0.

Capability-driven backfill and probes produced 26 completed attempts across 70 records and a final 20-unique-file automatic-success review set. The remaining records were 36 unsupported and 8 failed. Successful capability evidence included 20 narrow font-size changes, 3 moves, 2 non-text resizes, and 1 synthetic benchmark price replacement.

The private artifact contains 20 before/after comparisons and 5 contact sheets. GitHub Actions run `32335503616` produced artifact `chatgpt-corel-operator-mutation-pilot-001` (ID `9394492395`) with a seven-day retention. Privacy checks found zero CDR/CDT/SQLite files and zero local path leaks.

## Natural language action planner

The action schema is model-agnostic and suitable for a future tool-calling model. This run used only `DeterministicMutationPilotPlanner`, marked `planner_is_ai: false`, to provide hermetic, reproducible mechanical plans. No claim of real natural-language reasoning is made.

Planner output must parse into the strict schema and pass policy validation before execution. Extra fields, raw COM payloads, multi-object vague scope, or unsupported operations fail closed.

## Target resolution

Supported selectors include stable object ID, unique Corel name, exact text, case-insensitive text, bounded regex, phone-like text, and price-like text. Zero matches or multiple matches do not cause a guess; they return an unsupported/review outcome.

The real pilot exposed blank Corel names. The runtime now maps deterministic inspector IDs directly to live objects without renaming source or working-copy objects.

## Validation / refinement loop

The structured refinement policy permits at most three attempts. It may make only bounded corrections already allowed by the action policy. It cannot redesign the document, broaden target scope, invent customer content, or loop indefinitely. Unresolved tasks return `NEEDS_REVIEW`.

## Batch operator

The 200-file census served as the non-destructive batch pilot: 198 complete and 2 failed, with per-file subprocess isolation and resumable state. The 70 mutation attempt records were split into bounded primary/backfill/capability runs; 20 unique automatic successes were selected without discarding the unsuccessful records.

Corel process kills/restarts: 0. A single bad file did not terminate the batch. Source mutations: 0.

## MCP / tool-server status

`MCP_STATUS=NOT_IMPLEMENTED`

The safe typed Python contract is ready for an HTTP/JSON-RPC/MCP wrapper, but exposing it before improving target/capability reliability would not increase safe operator coverage. Raw COM, VBA, eval, and shell execution must never be exposed.

## Tests

- Full pytest: 343 passed, 1 third-party deprecation warning
- Source-only compile: passed for `training/`, `tests/`, and repository-root Python modules
- `git diff --check`: passed before commit
- Full `python -m compileall -q .`: the project sources compile, but the command returns 1 because the ignored Python 3.11 training virtualenv contains PyTorch's Python-3.12-only `py312_intrinsics.py`. No project file failed compilation.

Hermetic tests cover source-overwrite prevention, working-copy policy, strict plan validation, ambiguity, stable IDs, rollback, timeout/retry, batch resume/isolation, unexpected object changes, refinement bounds, artifact privacy, and path sanitization. CI does not require Corel, private CDRs, GPU, or models.

## Privacy / source safety

- Source archive is immutable and never receives `Save`.
- All editable outputs are Corel-created working-copy CDRs under ignored workspace.
- Original stat/hash evidence is verified after real mutation pilots.
- Source mutations detected: 0.
- The public repository contains no company CDR, preview, database, private manifest, or absolute archive path.
- Visual evidence is confined to the verified private repository.

## Performance

- Census completed-file median: 15.440 s
- Census completed-file p95: 55.958 s
- Census completed-file mean: 24.714 s
- Longest completed census file: 210.810 s
- Final timeout ceiling: 300 s

Export and document-open latency dominate. Reliability and source safety were prioritized over micro-optimization.

## Known limitations

- Safe automatic edits require exactly one defensible target.
- Most automatic success evidence is narrow font-size adjustment; move, resize, and replacement evidence is smaller.
- Active-page object mutation is implemented; comprehensive multi-page targeting is not.
- Visual equivalence and aesthetic improvement are not automatically asserted.
- Two census files still time out.
- Eight mutation attempts failed and 36 were unsupported across the extended probe set.
- No real LLM was used, and no MCP adapter is enabled.

## Remaining blockers

- Increase safe target coverage without weakening ambiguity rules.
- Add more real evidence for text replacement, transform, and multi-action transactions.
- Diagnose the two long-running timeout documents with a separately bounded Corel profiling path.
- Add multi-page target addressing and page-scoped postconditions.

## Next 3 priorities

1. Expand exact target resolution and page-scoped addressing using real unsupported cases, preserving fail-closed behavior.
2. Run a larger controlled scale test of the existing operator with more operation-balanced tasks and human visual review of the private artifact.
3. Only after reliability improves, expose the same typed policy-gated service through a minimal local tool server; never expose raw COM.

## Final metric block

```text
CENSUS_FILES=200
COREL_OPEN_RATE=99.0%
INSPECT_RATE=99.0%
SAVE_REOPEN_RATE=99.0%
PNG_EXPORT_RATE=99.0%
PDF_EXPORT_RATE=99.0%
SAFE_EDIT_ELIGIBLE_RATE=99.0%

MUTATION_PILOT_FILES=20
AUTO_SUCCESS=12
SUCCESS_WITH_WARNING=0
NEEDS_REVIEW=0
UNSUPPORTED=3
FAILED=5

EXTENDED_MUTATION_ATTEMPTS=70
EXTENDED_AUTO_SUCCESS=26
EXTENDED_UNSUPPORTED=36
EXTENDED_FAILED=8
UNIQUE_VERIFIED_MUTATION_FILES=20

BATCH_FILES=200
BATCH_AUTO_SUCCESS=198
BATCH_NEEDS_REVIEW=0
BATCH_UNSUPPORTED=0
BATCH_FAILED=2

SOURCE_MUTATIONS=0

TEST_COUNT=343
TEST_STATUS=PASS

MCP_STATUS=NOT_IMPLEMENTED
```

## Final status

`COREL_OPERATOR_PARTIAL_BUT_USABLE`

The evidence supports safe, useful bounded operation on many real CDRs. It does not support arbitrary unattended editing or full archive scale-up yet.
