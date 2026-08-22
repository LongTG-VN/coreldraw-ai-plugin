# Corel Operator Production Reliability Report

# RESULT

`COREL_OPERATOR_PRODUCTION_RELIABILITY_PARTIAL`

The operator now has trustworthy page-anchored Visual QA, bounded dependency-aware mutation validation, exact save/reopen accounting, and balanced real evidence for four useful operation families. It is not production-ready because terminal failure is 6.67%, text replacement has only 11 successful samples, and 22 prior page/pasteboard cases still lack trustworthy canonical visual evidence.

# GIT

- Branch: `codex/corel-operator-production-reliability`
- Starting checkpoint: `e05a9f64491e43a169c2a9a9bec9038653e10074`
- Milestone commits:
  - `1aedfe9 fix(qa): add page-anchored canonical Corel previews`
  - `f81ee19 feat(operator): add balanced production reliability safeguards`
  - `9748df7 fix(operator): close balanced reliability validation gaps`

# BASELINE

The Run2 checkpoint compiled, passed `356` hermetic tests, and passed `git diff --check`. Its scale evidence was safe but operation-imbalanced and visually over-conservative because raster dimensions depended on content.

# SOURCE SAFETY

All real mutations were made on working copies. Each task bound original file size, modification time, and SHA-256 before operation and verified them afterward. Original company files were never saved, renamed, moved, deleted, or overwritten.

Source mutations across the dimension investigation, 32-case reevaluation, 11-failure replay, ambiguity controls, and 120-task balanced pilot: `0`.

# PREVIOUS RUN METRICS

- automatic success: 40;
- needs review: 32;
- unsupported: 17;
- failed: 11;
- executed/save/reopen/editable: 72/72;
- median: 26.054 seconds;
- p95: 81.726 seconds.

# EXPORT DIMENSION ROOT CAUSE

Three representative real cases reproduced the issue. Page dimensions, document units, and object counts stayed constant, while `MaintainAspect=true` allowed Corel's current-page exporter to return dimensions based on changing artwork bounds. `MaintainAspect=false` fixed requested raster dimensions only after the export area was explicitly anchored to the page bounding box. Generic image resizing and cropping were rejected as invalid evidence repair.

# CANONICAL PAGE EXPORT

`canonical_page_dimensions` deterministically converts verified page geometry and DPI to a bounded raster. Corel receives the exact pixel dimensions, current-page range, page bounding box, and disabled aspect auto-adjustment. The emitted raster must exactly match the expected dimensions. Legacy documents that reject explicit page-area export fail closed.

# VISUAL QA V2

Visual QA V2 combines before/after structural inspection, canonical page evidence, explicit target IDs, a padded union of target boxes, and raster change-scope metrics. Structural regressions fail; bounded unexpected raster change requires review; severe outside-scope change fails. The output explicitly records that it is not aesthetic judgment.

See `docs/COREL_OPERATOR_VISUAL_QA_V2.md`.

# 32-CASE REEVALUATION

- reevaluated: 32;
- upgraded to automatic success: 10;
- still needs review: 0;
- confirmed regression: 0;
- evidence insufficient: 22;
- source mutations: 0.

The 22 evidence-insufficient cases were not promoted. Most involved a target on the pasteboard outside a blank active page or a legacy document that could not produce an explicit page-area export. No separate V2 review artifact was created because there were zero `STILL_NEEDS_REVIEW` cases.

# FAILURE ROOT CAUSES

The previous 11 failures clustered into six collateral-bounding-box policy cases, four TextRange/COM cases, and one worker-runtime case. Exact replay fixed 2, held 6 for review, left 2 failed, and marked 1 not replayable. Nine therefore remain unresolved; no easier substitute tasks were used.

# TEXT RANGE HARDENING

TextRange operations now reacquire the live shape for each bounded retry and require an exact postcondition. Silent no-op behavior on some legacy artistic numeric text was reproduced and safely rolled back. No broad page-level replacement fallback was enabled, and vulnerable numeric-only display texts are excluded from deterministic replacement selection.

# DEPENDENCY-AWARE POSTCONDITIONS

Only proven direct parents or the same text frame may be declared dependencies. The validator checks the relationship and property allowlist. Unrelated object geometry, content, styling, identity, and page changes remain protected. Multi-action changes to the same target are merged into the intended property scope.

# BALANCED PILOT DESIGN

The deterministic pilot contains 120 tasks: 30 text replacements, 30 moves, 30 resizes, and 30 multi-action transactions. It spans 53 unique real source documents with 67 transparent cross-lane reuses. It uses no LLM and performs no aesthetic filtering.

# TEXT REPLACE RESULTS

- attempted: 30;
- automatic success: 11;
- needs review: 1;
- unsupported: 15;
- failed: 3;
- persisted/save-reopen pass: 12.

# MOVE RESULTS

- attempted: 30;
- automatic success: 26;
- needs review: 0;
- unsupported: 1;
- failed: 3;
- persisted/save-reopen pass: 26.

# RESIZE RESULTS

- attempted: 30;
- automatic success: 27;
- needs review: 0;
- unsupported: 2;
- failed: 1;
- persisted/save-reopen pass: 27.

# MULTI-ACTION RESULTS

- attempted: 30;
- automatic success: 26;
- needs review: 0;
- unsupported: 3;
- failed: 1;
- persisted/save-reopen pass: 26.

# AMBIGUITY CONTROL RESULTS

Five deliberately ambiguous controls were presented. All five were safely refused before transaction execution; none mutated a source or working document automatically.

# SAVE / REOPEN

Persisted executed outputs: 91. Save/reopen/editability pass: 91. Fail: 0. Pass rate: 100%. Six additional transactions reached mutation but failed later policy/postcondition checks and were rolled back; they are not included in the persisted output denominator.

# VISUAL QA RESULTS

Among 91 persisted executed outputs, 90 were automatic success and one required review. Automatic success rate was 98.9011%; needs-review rate was 1.0989%. The one review result was retained rather than relabeled.

# PERFORMANCE

- median: 24.100390 seconds;
- p90: 57.700140 seconds;
- p95: 76.985266 seconds.

# COREL STABILITY

- Corel version: 22.0.0.412;
- crashes: 0;
- COM reconnects: 0;
- bounded worker timeouts: 2;
- infinite retry: none.

# MCP REGRESSION

Protocol and safety tests confirm loopback-only serving, explicit mutation confirmation, sanitized inventory identifiers, no arbitrary source paths, no raw COM exposure, no shell/VBA execution, and no increase in mutation authority. `ControlledInstructionPlanner` remains deterministic with `planner_is_ai=false`.

# TESTS

Final local verification passed source compile and `398` tests, with one third-party Starlette/httpx deprecation warning. The hermetic suite covers canonical export, Visual QA V2, dependency rules, TextRange retry/reacquisition, rollback, save/reopen accounting, balanced selection, ambiguity refusal, source immutability, review-artifact sanitation, and MCP safety. CI does not require CorelDRAW, private data, GPU, an LLM, or the private review repository.

# PRIVACY

Public code and documentation contain no customer paths, customer filenames, source binaries, databases, or private manifests. Visual evidence exists only in the private review repository. The published reliability artifact contains 91 `BEFORE | AFTER | DIFF` comparisons and no source design files.

# PRODUCTION RELIABILITY GATE

| Gate | Actual | Result |
| --- | ---: | --- |
| Source mutations | 0 | PASS |
| Save/reopen among persisted executed outputs | 100% | PASS |
| Terminal failure | 6.6667% | **FAIL**; target <=5% |
| Automatic success among executed | 98.9011% | PASS |
| Needs review among executed | 1.0989% | PASS |
| Meaningful text-replace evidence | 11 successes | **PARTIAL**; aim >=20 |
| Meaningful move evidence | 26 successes | PASS |
| Meaningful resize evidence | 27 successes | PASS |
| Meaningful multi-action evidence | 26 successes | PASS |

Final gate: `PRODUCTION_RELIABILITY_GATE_PARTIAL`.

# REMAINING BLOCKERS

1. Text replacement is under-covered: 11 successful samples, 15 unsupported targets, and unresolved legacy TextRange no-op behavior.
2. Terminal failure is 8/120 (6.67%), above the 5% gate; remaining failures include collateral relationship/identity changes and two bounded timeouts.
3. Page-anchored QA cannot yet provide trustworthy evidence for pasteboard-hosted artwork or some legacy page-area exports; 22 of the old 32 cases remain evidence-insufficient.

# NEXT 3 ACTIONS

1. Build a narrowly scoped legacy text capability probe that classifies object-local replacement support before transaction execution.
2. Model only empirically proven linked-effect/container dependencies and add timeout isolation for the two failing source profiles.
3. Add a pasteboard-aware but spatially grounded evidence mode, then rerun only the unresolved cases and another balanced gate pilot.

Next recommended mission: `OPERATOR_RELIABILITY_CONTINUATION`.
