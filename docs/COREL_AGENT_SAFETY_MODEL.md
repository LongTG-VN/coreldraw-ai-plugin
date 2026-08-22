# Corel Agent Safety Model

## Trust boundary

Planner output is always untrusted. The planner can propose a structured plan but cannot open arbitrary paths, call COM, run code, save a document, or bypass the transaction engine.

## Source invariant

Original company CDR files are immutable. Real mutations operate only on copied working documents. Source size, timestamp, and digest guards are checked before and after bounded real-Corel work. The overnight targeted pilot and the 200-file dry run detected zero source mutations.

## Modes

- `PLAN_ONLY`: parse and validate; execution is always denied.
- `DRY_RUN`: inspect, resolve, validate, persist; execution is always denied.
- `EXECUTE_CONFIRMED`: necessary but not sufficient. Policy, risk, and review gates still apply.

Silence or process continuation is never confirmation.

## Rejected authority

The semantic validator rejects unknown actions, arbitrary paths, traversal, shell or PowerShell, Python subprocess intent, raw COM, VBA, direct `Document.Save`, and delete-all intent. MCP binds only to loopback and exposes no generic code or filesystem tool.

## Privacy

- Inventory IDs are opaque.
- Context text is hidden unless explicitly requested.
- Error strings normalize path separators and replace the approved archive root.
- SQLite jobs, dry-run records, previews, and source-derived data stay in ignored workspace directories.
- Public tests use synthetic fixtures.

## Confirmation and risk

Unique exact text replacement is the only current low-risk mutation classification. Geometry, rotation, and typography changes are medium risk and require review. Disallowed plans remain non-executable even when a request says `EXECUTE_CONFIRMED`.

## Failure behavior

Target ambiguity, missing targets, invalid schema, policy rejection, failed postconditions, visual-QA review, save/reopen failure, and export failure have distinct error codes. Existing Corel transaction logic rolls back a logical mutation when a required postcondition fails.

## Security regression surface

Hermetic tests cover extra-field rejection, path injection, unsafe code/action content, opaque IDs, loopback MCP, explicit confirmation, duplicate prevention, output naming, and source-path sanitization. Real Corel integration remains separate from CI.
