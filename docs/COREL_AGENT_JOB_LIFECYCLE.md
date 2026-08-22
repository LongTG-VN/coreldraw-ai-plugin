# Corel Agent Job Lifecycle

## Persisted job

`CorelOperatorJobV1` records job and document IDs, normalized request, planner provenance, plan hash, source-bound task fingerprint, risk, state, execution flags, validation, outputs, and an audit trail. Jobs are stored in a local ignored SQLite database.

## States

```text
CREATED -> INSPECTED -> PLANNED -> VALIDATED
                                      |-> WAITING_CONFIRMATION -> EXECUTING
                                      |                         -> VALIDATING
                                      |                         -> COMPLETED
                                      |                         -> NEEDS_REVIEW
                                      |                         -> ROLLED_BACK
                                      |                         -> FAILED
                                      -> COMPLETED (dry-run accounting only)
```

Inspection, planning, and validation failures may move to `FAILED`; uncertainty may move to `NEEDS_REVIEW`. Terminal states cannot transition further through the store.

## Fingerprinting

The deterministic task fingerprint hashes:

1. full source SHA-256;
2. normalized instruction;
3. strict plan hash.

Submitting the same source/request/plan returns the existing job rather than creating a second execution candidate. A completed job is not silently replayed.

## Resume

SQLite commits each job independently. The scale dry-run also writes atomic JSON state per document. After process or Corel restart, completed document IDs are skipped and persisted jobs are reused.

## Output naming

Generated outputs use:

```text
<design_id>__<job_id>__vNNN.<cdr|pdf|png>
```

Only bounded identifiers, versions 1–9999, and the three approved extensions are accepted. Collision handling must increment or refuse; silent overwrite is forbidden.

## Current limitation

The overnight checkpoint verifies persistence and dry-run resume. It does not expose a general unattended execute/resume CLI and does not prove batch mutation recovery.
