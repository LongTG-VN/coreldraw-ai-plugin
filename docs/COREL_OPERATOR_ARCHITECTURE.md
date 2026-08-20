# CorelDRAW AI Operator Architecture

## Purpose

The operator makes bounded edits to existing, editable CorelDRAW documents. It is not a document reconstruction system and does not convert a CDR into a reduced intermediate representation before editing. CorelDRAW remains the owner of the complete document state, including objects the operator does not understand.

## Safety boundary

```text
human or planner intent
        |
        v
MutationPlanV1 (strict JSON contract)
        |
        v
target resolver + policy gate
        |
        v
Corel-created working copy (.cdr)
        |
        v
DesignTransactionEngine
        |
        v
CorelDRAW COM (serialized by CorelDrawBridge)
        |
        v
postcondition validation -> save/reopen OR undo
```

Neither a language model nor a future MCP client may submit raw COM, VBA, Python, shell, or arbitrary method names. The only executable inputs are validated `MutationPlanV1` operations.

## Source-file invariant

Company source files are resolved under an explicit archive root and restricted to `.cdr` or `.cdt`. Before any operation, the operator records source size, modification time, and creation/change time. Corel opens the source only long enough to execute `SaveAs` to a new `.cdr` below the operator workspace. All mutation, save, reopen, PNG, and PDF work happens on that copy. The source stat guard is checked again at the end.

Timeout recovery closes a document without saving only when it is either a generated working copy below the operator workspace or the exact timed-out source path supplied to the worker. The exact-source path is resolved, matched case-insensitively, closed with `Close()` (never `Save()`), and checked against the source stat guard afterward. Recovery never closes an unrelated active document and never kills CorelDRAW automatically.

## Structured contracts

- `TargetSelectorV1`: object ID, Corel name, exact text, case-folded text, bounded regex, phone, or price selector.
- `MutationActionV1`: one operation, one target, one value, explicit precondition, and a maximum scope of one object.
- `MutationPlanV1`: 1–50 bounded actions, provenance (`human`, `fixture`, `deterministic`, or `llm`), zero expected object-count change, mandatory rollback policy, and metadata.
- `OperatorExecutionResultV1`: result class, sanitized source token, target IDs, counts, lifecycle evidence, rollback/editability flags, warnings, and timings.

Allowed result classes are `AUTO_SUCCESS`, `SUCCESS_WITH_WARNING`, `NEEDS_REVIEW`, `UNSUPPORTED`, and `FAILED`.

## Targeting rules

The resolver fails closed when no object matches, more than one object matches, or the selected Corel object name is not unique. It never chooses the first visual or text match silently. A future planner can request a target, but only the deterministic resolver establishes whether the target is executable.

The current safe operator exposes:

- replace text;
- move to an absolute position;
- resize to positive absolute dimensions;
- rotate;
- set font family;
- set font size.

The lower-level Design API also supports creation, fill, ordering, alignment, distribution, grouping, asset import, page resize, and deletion. Those operations are intentionally not enabled in `MutationPlanV1` yet because their preservation/postcondition rules have not passed the real-company mutation pilot.

## Transaction and rollback

Actions execute as one Corel command group through `DesignTransactionEngine`. A failed action closes the command group and calls Corel Undo. After a successful command group, the operator snapshots the working copy and verifies:

- object count did not change;
- the object identity set did not change;
- every non-target object retained all tracked properties;
- each target changed only properties allowed for its operation.

If a postcondition fails, the operator calls Undo and verifies the pre-transaction snapshot was restored. A copy is saved only after these checks pass.

## Editable reopen verification

After save, the operator closes and reopens the generated CDR through CorelDRAW. Editability is considered verified only when Corel exposes the same object count and stable inspected object-ID set. Preview images are evidence only; they are not the primary output.

## Planner boundary

`StructuredOperatorPlanner` is model-agnostic. The real mutation pilot uses `DeterministicMutationPilotPlanner`, explicitly marked `planner_is_ai: false`. It selects a bounded mechanical operation (font size by five percent, move by one millimetre, resize by one percent, or an explicitly marked benchmark phone/price replacement) on a uniquely addressable object. Replacement values exist only in generated working copies and are tagged `benchmark_sample_data: true`; they are never represented as customer-supplied data. The planner exists to test operator coverage, not to judge aesthetics.

Future LLM output must pass `validate_planner_output`. Invalid or extra fields—including raw COM payloads—are rejected.

## Batch isolation and resume

Long real-Corel jobs run one file per Python subprocess. Every result is persisted to SQLite before the next file starts. A worker has a hard wall-clock timeout; failures are categorized and do not silently remove a file from the denominator. Explicit `--retry-failures` is required to rerun failed census entries.

The timeout worker may be terminated, but CorelDRAW itself is not killed automatically. Recovery only closes a proven generated working copy. This avoids losing unrelated unsaved user work.

## Privacy

Operator SQLite databases, generated CDRs, source paths, and company previews remain under ignored `training/workspace/`. Public documentation contains aggregate metrics and opaque `source:<hash>` tokens only. Visual mutation evidence may be published only to the verified private review repository after path-leak and forbidden-extension checks.

## Known limitations

- Inspection currently enumerates every object on the active page and records total page count; full multi-page object mutation is not enabled.
- Cooperative batch timeout reporting exists in the generic runner; the real census and mutation pilot use hard subprocess isolation.
- The safe operator does not yet expose create/delete/group/align/distribute operations.
- Exact visual equivalence is not asserted. The operator verifies structural preservation, editable reopen, and bounded property changes.
- No MCP server is enabled. The Python contract must remain stable before an MCP wrapper is justified.
