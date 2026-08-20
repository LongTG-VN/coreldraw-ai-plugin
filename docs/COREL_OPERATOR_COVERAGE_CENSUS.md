# Corel Operator Coverage Census

## Scope

This census measures whether CorelDRAW can operate on real company CDR files while preserving Corel as the document owner. It does not measure full `DesignDocument` reconstruction.

The sample contains 200 deterministic entries selected across five file-size strata from the existing archive inventory. Stable source tokens make the selection reproducible without exposing filenames or paths. Every file ran in its own subprocess with a hard timeout and persisted state.

## Operator-eligible definition

A file is operator-eligible only when all of the following succeed:

- CorelDRAW opens the source;
- object enumeration succeeds;
- CorelDRAW creates a separate working-copy CDR;
- the working copy closes and reopens;
- the reopened objects remain addressable/editable.

The original archive file is not saved. Size, modification time, and creation/change time are checked before and after processing.

## Results

| Metric | Result |
| --- | ---: |
| Sample size | 200 |
| Corel open | 198/200 (99.0%) |
| Document inspection | 198/200 (99.0%) |
| Object enumeration | 198/200 (99.0%) |
| Text enumeration | 198/200 (99.0%) |
| Bitmap enumeration | 198/200 (99.0%) |
| Vector enumeration | 198/200 (99.0%) |
| Group enumeration | 198/200 (99.0%) |
| Page enumeration | 198/200 (99.0%) |
| Pasteboard enumeration | 198/200 (99.0%) |
| Snapshot | 198/200 (99.0%) |
| Save as working copy | 198/200 (99.0%) |
| Reopen working copy | 198/200 (99.0%) |
| Editable reopen | 198/200 (99.0%) |
| PNG export | 198/200 (99.0%) |
| PDF export | 198/200 (99.0%) |
| Close safety | 200/200 (100%) |
| Overall operator-eligible | 198/200 (99.0%) |
| Source mutations | 0 |

Successful files had mean total processing time 24.714 seconds, median 15.440 seconds, and p95 55.958 seconds. The longest completed file took 210.810 seconds.

## Failure Pareto

The final failure set contains two `TIMEOUT` entries after an explicit retry of the five initial failures with a 300-second ceiling.

| Category | Count | Sample rate | Failure share | Priority |
| --- | ---: | ---: | ---: | --- |
| Timeout | 2 | 1.0% | 100% | Medium |

Three of five initially timed-out files recovered during the bounded retry. The two remaining files stay in the denominator and remain failed; they were not replaced with easier files.

## Coverage fixes validated during the run

- one subprocess per file prevents one bad document from terminating the batch;
- results and attempts persist in SQLite for resume and explicit failure retry;
- a hard wall-clock timeout replaces cooperative-only cancellation for real Corel work;
- generated working copies are closed without saving during recovery;
- an exact timed-out source may be closed without saving only after path identity checks, followed by the source stat guard;
- CorelDRAW is not killed automatically, protecting unrelated unsaved user work;
- paths and errors in reports are sanitized to opaque source tokens.

## Limitations

- The deterministic sample is stratified by inventoried file size. Object/page/bitmap complexity is measured after opening rather than used as a pre-open sampling dimension.
- Object mutation is currently active-page focused even though page count is enumerated.
- The census proves operational compatibility for this sample, not the entire archive.
- The two timeout cases require separate diagnosis before claiming full coverage.

## Local evidence

Detailed SQLite/CSV/JSON evidence is stored under ignored `training/workspace/company_archive/operator_census/`. It is intentionally excluded from Git because it is derived from private company data.
