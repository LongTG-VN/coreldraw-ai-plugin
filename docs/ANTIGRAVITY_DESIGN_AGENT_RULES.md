# Antigravity Design Agent Rules

## Golden rule

Antigravity operates on CorelDRAW through the existing high-level local API.
Routine design work must follow this priority:

1. Design API (`/api/v1/design/*`)
2. validated transaction operations
3. an intentional, tested extension to the Corel integration layer
4. GUI/mouse/keyboard automation only as a last resort

The forbidden default is new arbitrary `pywin32` code that mutates CorelDRAW
outside `CorelDrawBridge`. Direct COM code is acceptable only when deliberately
extending the integration layer and must carry fake-adapter tests plus a real
local smoke when possible.

## Safe design loop

```text
read brief
→ GET snapshot and objects
→ preserve supplied business data
→ create/mutate through one bounded transaction
→ inspect transaction report
→ run design/check
→ render-preview
→ inspect the result
→ make bounded edits or undo
→ check again
→ save-as .cdr (or save an already named CDR)
→ export PNG/PDF derivatives
```

Never continue blindly after HTTP 409/503. On a failed transaction, read
`rolled_back`, `end_group_error`, and `rollback_error`, refresh the snapshot,
and use `/api/v1/design/undo` only when the actual document state warrants it.

## Object targeting

- Prefer unique Corel shape names returned as `name`/`shape_name`.
- Generated names follow `ai_<role>_<8 hex>`; supplied names are retained.
- Target by stable semantic name, role/group/layer context from the snapshot,
  not by statements such as “click near the top-right”.
- Names are scoped to the active document. Re-open/new/delete invalidates prior
  assumptions; refresh the snapshot after every document lifecycle operation.
- The current lookup returns a matching name, so duplicate names are unsafe.
  Antigravity must create unique names.

## Transaction rule

Mutations that form one logical edit belong in one transaction. For example,
enlarging a hero, shifting copy, and moving the CTA should be submitted as one
operation group. The current engine uses Corel command groups and one Undo on
failure. If Corel cannot end or undo the group, rollback is not guaranteed and
the error report says so.

Never combine unrelated risky work into a giant transaction. The hard limit is
200 operations; practical agent transactions should be much smaller and easy
to inspect.

## Business-data immutability

Antigravity may change visual presentation. It must not invent or silently
change prices, offers, discounts, dates, phone numbers, addresses, menu values,
brand names, legal/customer claims, or campaign facts. Missing facts remain
explicit placeholders. Synthetic values are allowed only in a clearly marked
benchmark with `benchmark_sample_data=true` and `customer_provided=false`.

## Editable output

- The primary deliverable is `.cdr`, not only PNG or `design.json`.
- Keep text as Corel text, shapes as vectors, groups as groups, and assets as
  independent imported objects wherever supported.
- Do not rasterize the whole page as a shortcut.
- Use `/api/v1/design/save-as` with an absolute `.cdr` path and
  `overwrite=false` first. Use `/api/v1/design/save` for later saves.
- PNG/PDF are derivatives for review/distribution, not substitutes for CDR.

## COM ownership and concurrency

Python is the sole COM owner. `CorelDrawBridge` initializes the COM apartment
for the current worker thread and serializes every session with a reentrant
lock. Do not run multiple API processes or independent COM controllers against
the same active Corel document. Model generation can run separately, but all
Corel mutations must funnel through one API process.

## Planner and research defaults

- Qwen3-1.7B plus the local LoRA remains an offline research fallback planner.
- v0.3.4 visual RAG is preserved but failed its quality gate and is disabled by
  default. Do not set `DESIGN_AI_VISUAL_RAG_ENABLED=true` in routine operation.
- v0.3.5 vision critic is preserved as standalone research code; it is not an
  approved default critic or human preference source.
- Automated/heuristic/critic outputs must never be stored as human labels.
- Do not train a preference model until the explicit human-data gate passes.

## File and data safety

- Use safe document endpoints, absolute paths, strict extensions, and
  `overwrite=false` unless overwrite is an explicit user instruction.
- The local API is unauthenticated. Keep it bound to `127.0.0.1`.
- Never expose arbitrary filesystem access or this API to the network.
- Preserve ignored `training/artifacts`, `training/data`, checkpoints, model
  caches, downloaded assets, and human review records.
- Preserve license/provenance flags. The current trained planner/reference
  lineage is research-only and not commercial-approved.

## Stop conditions

Stop and report the exact state when Corel COM is unavailable, the active
document is unexpected, an object ID is stale, save target exists, path is
rejected, transaction rollback fails, or data/license provenance is unclear.
Do not “repair” these conditions by overwriting data or inventing content.
