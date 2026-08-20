# CorelDRAW AI Operator — Run #2 Production Readiness

## Decision

`COREL_OPERATOR_RUN2_PARTIAL_NOT_PRODUCTION_READY`

Run #2 converts the Run #1 typed operator into a local policy-gated MCP service and a conservative task agent, fixes stable targeting of unnamed/duplicate-named Corel objects, adds deterministic visual-integrity QA, and completes a real 100-file mutation scale test.

It is safe enough for supervised local use on bounded tasks. It is not ready for unattended arbitrary production editing: 32 of 72 executed mutations require visual review, 17 of 100 inputs had no defensible bounded task, 11 failed after bounded retry, and operation evidence remains heavily concentrated in small font-size changes.

No Qwen, Antigravity, training, Gold promotion, Visual RAG, vision critic, or aesthetic model ran.

## Run #1 baseline

The frozen Run #1 checkpoint is commit `2eced6530aa0edb06529de7a9a8399a4111994ff`.

- Census: 198/200 real CDR files completed; two bounded timeouts; zero source mutations.
- Primary mutation pilot: 12/20 automatic successes, 3 unsupported, 5 failed.
- Extended attempt set: 26 complete, 36 unsupported, 8 failed across 70 records.
- MCP status at that historical checkpoint: not implemented.

Run #1 evidence remains unchanged in `docs/COREL_OPERATOR_24H_REPORT.md`.

## Largest bottleneck fixed

The real documents frequently contained blank or duplicate Corel object names. Runtime inspection already produced stable `object_<n>` identifiers, but target resolution and deterministic planning still required unique Corel names. This rejected otherwise unambiguous objects.

Run #2 makes the stable inspector object ID authoritative for live targeting while preserving fail-closed behavior:

- no source or working-copy object is renamed;
- ambiguous text/name selectors still fail;
- object IDs remain page/order-derived inspection identities;
- the runtime resolves exactly one live object by that ID;
- postconditions still detect changes to non-target objects;
- page count, page geometry, and document units are now protected postconditions.

The unsupported rate fell from 36/70 in the heterogeneous Run #1 extended attempts to 17/100 in the Run #2 sample. This is encouraging but not a controlled causal comparison because selection and visual-QA rules differ.

## Local MCP and task agent

The MCP server exposes seven bounded tools documented in `docs/COREL_OPERATOR_MCP_SERVER.md`. It uses opaque inventory IDs, serializes Corel calls, creates new task workspaces, rejects arbitrary paths, and requires explicit execution confirmation.

`ControlledInstructionPlanner` is a deterministic explicit-command parser, not an AI planner. It supports exact quoted text replacement, unique phone/price replacement, object-ID font size, move, resize, and bounded scale-up. Unsupported or ambiguous requests stop without mutation.

## Real production-style task smoke

A real CDR working-copy smoke executed one explicit benchmark price instruction using the same task-agent service:

- agent status: `AUTO_SUCCESS`;
- planner: deterministic, `planner_is_ai=false`;
- action count: 1 exact text replacement;
- object count: 12 before, 12 after, 12 after reopen;
- transaction: committed;
- editable reopen: verified;
- source unchanged: verified;
- copy time: 6,011.8 ms;
- transaction time: 551.1 ms;
- total time: 26,572.7 ms;
- visual QA: PASS;
- changed-pixel ratio: 0.006872424;
- mean absolute difference: 0.26997.

The replacement was explicit benchmark sample data, not inferred customer data.

## Real 100-file scale test

Configuration:

- real company CDR sample: 100;
- selection seed: `corel-operator-run2-v1`;
- planner mode: automatic deterministic pilot;
- per-file subprocess timeout: 240 seconds;
- maximum attempts: 2;
- processing: sequential Corel ownership;
- source mode: read-only with per-file stat guard.

Results:

| Result | Count | Rate |
|---|---:|---:|
| Technical visual-QA PASS / `AUTO_SUCCESS` | 40 | 40% |
| Executed and editable, held for visual review | 32 | 32% |
| Unsupported / no safe target | 17 | 17% |
| Failed after bounded handling | 11 | 11% |
| Total | 100 | 100% |

Execution evidence:

- executed, saved, reopened, and still editable: 72/100;
- source mutations: 0/100;
- visual QA PASS among executed: 40/72 (55.6%);
- visual QA review among executed: 32/72 (44.4%);
- median wall time: 26.054 seconds/file;
- p95 wall time: 81.726 seconds/file;
- first-attempt terminal records: 89;
- second-attempt terminal records: 11.

Operation mix:

| Operation mode | Count |
|---|---:|
| font size +5% | 72 |
| resize +1% | 4 |
| move +1 mm | 2 |
| benchmark phone replacement | 2 |
| benchmark price replacement | 2 |

Operation counts include planner attempts and therefore include some failures. Replacement values were marked `benchmark_sample_data=true`; they are not customer-provided values.

## Failure analysis

Terminal error codes across unsupported/failed inputs:

- `NO_SAFE_TEXT_TARGET`: 17;
- `POLICY_OR_VALIDATION_FAILURE`: 6;
- `COREL_RUNTIME_FAILURE`: 4;
- `WORKER_FAILURE`: 1.

The six policy failures were caused by observed non-target bounding-box changes, so rollback/fail-closed behavior correctly prevented automatic acceptance. Four runtime failures originated in Corel `TextRange` mutation errors. One worker failure remained isolated; it did not stop the batch.

All 32 visual-review outcomes carried `PREVIEW_DIMENSION_CHANGED`. A read-only real inspection of one representative source and its working copy confirmed identical page geometry (102 × 69 mm), object count (5), and units despite different exported PNG dimensions. Corel's current-page export honors the export range, but the produced raster size may still vary after content changes. Run #2 deliberately keeps these results for human review rather than resampling them into an automatic PASS.

Corel's API documents `cdrCurrentPage=1` and the `Document.ExportEx` range/options contract: <https://community.coreldraw.com/sdk/api/draw/22/e/cdrExportRange>.

## Visual QA

Visual QA checks:

- preview path remains under the approved workspace;
- input is PNG/JPEG;
- before and after exports exist;
- same-size frames have a bounded changed-pixel ratio;
- no visible change and excessive frame change are rejected;
- dimension changes are held for review;
- `aesthetic_judgment` is always false.

The local ignored review package contains all 72 executed before/after pairs:

```text
training/workspace/company_archive/operator_run2_scale_100_review/
```

- comparisons: 72;
- contact sheets: 18;
- automatic PASS comparisons: 40;
- NEEDS_REVIEW comparisons: 32;
- CDR/CDT/SQLite included: 0;
- local path leaks: 0;
- human preference collected: false;
- Gold certification: none.

The package is local and ignored. It was not published or committed.

## Realistic production workflow

Recommended supervised flow:

```text
inventory file ID
 -> corel_get_document / corel_list_objects
 -> corel_plan_task
 -> human/tool-policy approval
 -> corel_run_task(execution_confirmed=true)
 -> transaction and postconditions
 -> save/reopen editable CDR
 -> corel_visual_qa
 -> accept PASS or route NEEDS_REVIEW to a person
```

The source stays immutable. Every execution uses a new task ID and a new Corel-created working copy.

## Production blockers

1. Resolve or explicitly normalize Corel export-dimension variance without hiding page/crop regressions.
2. Reduce the 11% terminal failure rate, especially Corel TextRange exceptions and policy-detected collateral bbox changes.
3. Expand real evidence beyond font-size edits to balanced text replacement, move, resize, rotation, multi-action transactions, and multi-page targeting.
4. Add a human decision step for the 32 visual-review cases and measure false-positive/true-regression rates.
5. Validate a tool-calling AI planner separately; the current task planner is intentionally deterministic.

## Readiness matrix

| Capability | Status |
|---|---|
| Source immutability | VERIFIED (0 mutations/100) |
| Working-copy CDR save/reopen | VERIFIED (72/72 executed) |
| Editable object preservation | VERIFIED for executed sample |
| Stable unnamed-object targeting | IMPLEMENTED and unit/real exercised |
| Transaction/postcondition safety | IMPLEMENTED; collateral changes fail closed |
| Local MCP boundary | IMPLEMENTED |
| Autonomous bounded task loop | IMPLEMENTED, deterministic only |
| Visual integrity QA | IMPLEMENTED, conservative |
| Arbitrary natural-language editing | NOT SUPPORTED |
| Aesthetic QA | NOT IMPLEMENTED |
| Unattended production readiness | NOT READY |

## Verification

Final verification commands:

```powershell
python -m compileall -q training tests
python -m pytest -q
git diff --check
```

Local result on 2026-08-20: source compile passed; `356 passed` with one third-party Starlette/httpx deprecation warning; `git diff --check` passed.

CI remains hermetic: no Corel, private archive, GPU, model, or company preview is required.

## Next 3 actions

1. Build a page-anchored export comparison or verified image-registration step and human-label the current 32 dimension-change cases.
2. Run an operation-balanced supervised pilot that targets at least 20 successful cases each for text, transform, resize, and multi-action transactions.
3. After the failure and review rates meet an explicit gate, connect a tool-calling planner to the existing MCP contract without extending its mutation authority.
