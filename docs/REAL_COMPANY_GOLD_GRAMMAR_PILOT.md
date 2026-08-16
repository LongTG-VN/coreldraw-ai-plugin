# Real Company Gold Grammar Pilot

## Purpose

This pilot tests a causal, non-AI path:

```text
real company archive CDR
-> Corel inspection
-> DesignDocument
-> provisional GoldDesignGrammar
-> bounded adaptation
-> real editable Corel CDR
```

It does not train a model, invoke Qwen or Antigravity, certify Gold, or make an
aesthetic claim. A source advances only when every earlier stage has real,
source-bound evidence.

## Fixed source cohort

The cohort is fixed by the private Round 2 review source of truth:

- `CDR_000159`
- `CDR_000020`
- `CDR_000401`
- `CDR_000442`
- `CDR_000295`

All five are `GOLD_CANDIDATE_FINAL` visual-review candidates. None is
`HUMAN_CERTIFIED_GOLD`.

## Rights and certification

The pilot uses the following fail-closed values:

```text
source_type: COMPANY_ARCHIVE_CDR
human_quality_status: GOLD_CANDIDATE_FINAL
human_certified_gold: false
rights_status: UNKNOWN
project_owned: false
commercial_allowed: false
```

Folder location is not treated as proof of ownership or commercial rights.
The existing human-certified company grammar gate remains unchanged.

## Source safety

Each archive source is hashed and stat-recorded, copied to the ignored pilot
workspace, and verified again after processing. Corel opens only `source_copy.cdr`
for this experiment. All inspected documents are closed without `Save`.

Local-only artifacts live under:

```text
training/workspace/company_archive/gold_source_pilot/
```

That directory contains source paths and company CDR copies and must never be
committed or published.

## Native Corel verification

CorelDRAW `Version 22.0.0.412` opened all five copies with the verified
millimetre enum `3`. Each source produced a bounded native PNG preview, and
`source_save_called` remained false.

The inspector now explicitly sets the opened document to millimetres before
reading page and shape geometry. Raw geometry is retained in object metadata;
off-page geometry is marked `bbox_clipped_to_page` rather than silently
presented as a valid page-bound object.

## Extraction gate and negative result

The selected CDR files are production workspaces containing artwork on the
Corel pasteboard outside the active page. Four sources have every inspected
object outside the active page; the fifth has 137 of 311 objects outside.

| Design ID | Objects | Outside active page | Rate |
|---|---:|---:|---:|
| `CDR_000159` | 24 | 24 | 100.0% |
| `CDR_000020` | 30 | 30 | 100.0% |
| `CDR_000401` | 311 | 137 | 44.05% |
| `CDR_000442` | 50 | 50 | 100.0% |
| `CDR_000295` | 88 | 88 | 100.0% |

The current `DesignDocument` contract describes a bounded canvas and cannot
causally choose which pasteboard cluster is the intended design. Clamping all
objects into the page would destroy geometry and manufacture a false success.
Extraction therefore fails closed with `OBJECTS_OUTSIDE_ACTIVE_PAGE`.

## Grammar and round-trip behavior

The candidate helper can extract a provisional, SHA-bound grammar from a valid
unowned archive `DesignDocument`. It records heuristic semantic assignments as
non-human and allows `UNKNOWN` when evidence is insufficient. It cannot widen
rights or create human Gold status.

No valid `DesignDocument` existed for this cohort, so:

- Gold grammars created: `0`
- control Corel reconstructions: `0`
- bounded adaptations: `0`
- generated editable CDRs: `0`

The invalid early clamped attempt is preserved only under the ignored local
workspace as negative evidence and is not counted as a result.

## Review gate

No source/control/adaptation review package was published because no source
passed the extraction and round-trip prerequisites. Aesthetic quality remains
`NOT_MEASURED`.

Before rerunning this exact cohort, the pipeline needs an explicit,
human-auditable artboard/pasteboard-region selection contract and a causal
strategy for arbitrary Corel curves/bitmaps. Those capabilities must preserve
the original source cluster without manual geometry repair.

