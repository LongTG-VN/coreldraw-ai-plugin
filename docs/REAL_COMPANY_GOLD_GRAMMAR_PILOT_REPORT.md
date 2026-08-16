# Real Company Gold Grammar Pilot Report

## RESULT

```text
REAL_COMPANY_GRAMMAR_PILOT_BLOCKED
```

The experiment found a real data-model blocker. The five selected company CDRs
render correctly in Corel, but their reviewed artwork lives partly or wholly on
the pasteboard rather than inside the active page. The current page-bound
`DesignDocument` extractor cannot choose an intended artboard without inventing
geometry.

## GIT

- Branch: `codex/real-company-gold-pilot`
- Starting SHA: `ba2d24b2a24ac69948f443b45c034e08cc3cbb28`
- Implementation commit: `4dea8db`
- Base branch preserved: `codex/company-gold-data-bootstrap`

## SOURCE RESOLUTION

All five exact IDs resolved through the autonomous review state and inventory:

| Design ID | Resolution | Final pilot status |
|---|---|---|
| `CDR_000159` | `RESOLVED` | `SOURCE_BLOCKED` |
| `CDR_000020` | `RESOLVED` | `SOURCE_BLOCKED` |
| `CDR_000401` | `RESOLVED` | `SOURCE_BLOCKED` |
| `CDR_000442` | `RESOLVED` | `SOURCE_BLOCKED` |
| `CDR_000295` | `RESOLVED` | `SOURCE_BLOCKED` |

Local resolution evidence:
`training/workspace/company_archive/gold_source_pilot/SOURCE_RESOLUTION.json`.
It contains local source paths and is intentionally ignored by Git.

## SOURCE SAFETY

- Original source CDRs opened by Corel: `0`
- Workspace copies created: `5`
- Full SHA-256 verified before/after: `5/5`
- Source size and mtime unchanged: `5/5`
- Source mutations detected: `0`
- Corel source-copy `Save` calls: `0`

## RIGHTS / CERTIFICATION

```text
source_type: COMPANY_ARCHIVE_CDR
human_quality_status: GOLD_CANDIDATE_FINAL
human_certified_gold: false
rights_status: UNKNOWN
project_owned: false
commercial_allowed: false
```

No candidate was promoted to Gold and no legal right was inferred from archive
location.

## NATIVE COREL PREVIEWS

Corel runtime: `Version 22.0.0.412` with document unit enum `3` (millimetres).

| Design ID | Native preview | Objects | Text | Bitmap | Vector | Groups |
|---|---|---:|---:|---:|---:|---:|
| `CDR_000159` | valid | 24 | 4 | 0 | 18 | 2 |
| `CDR_000020` | valid | 30 | 7 | 0 | 18 | 5 |
| `CDR_000401` | valid | 311 | 57 | 0 | 233 | 21 |
| `CDR_000442` | valid | 50 | 8 | 0 | 39 | 3 |
| `CDR_000295` | valid | 88 | 7 | 1 | 73 | 7 |

Native verification passed `5/5`. Preview generation was bounded and did not
write to archive sources.

## CDR → DESIGNDOCUMENT

Result: `0/5` valid documents.

The inspector originally exposed mixed-unit geometry; the pilot fixed this by
setting each opened document to Corel millimetres before inspection. The next
valid observation revealed pasteboard geometry:

| Design ID | Outside active page | Rate |
|---|---:|---:|
| `CDR_000159` | 24/24 | 100.0% |
| `CDR_000020` | 30/30 | 100.0% |
| `CDR_000401` | 137/311 | 44.05% |
| `CDR_000442` | 50/50 | 100.0% |
| `CDR_000295` | 88/88 | 100.0% |

The extractor now rejects clipped pasteboard geometry instead of normalizing a
distorted layout.

## EXTRACTION COVERAGE

- Native inspection object coverage: `503/503` objects enumerated
- Valid page-bound DesignDocument coverage: `0/5` sources
- Normalized bbox validity: not applicable; blocked before document creation
- Font metadata coverage: not promoted to a metric because extraction stopped
- Canvas deviation: not measured; an intended canvas cannot be inferred safely

## ROUNDTRIP CONTROL

No control reconstruction was sent to Corel. This is deliberate: a severely
incomplete or geometrically distorted `DesignDocument` is not a valid control.

```text
control_reconstructed.cdr count: 0
ROUNDTRIP_GOOD: 0
ROUNDTRIP_PARTIAL: 0
ROUNDTRIP_BAD / blocked before control: 5
```

## GOLD GRAMMAR EXTRACTION

No grammar was created from the five sources. The new helper supports only
provisional candidate extraction from a valid SHA-bound
`COMPANY_ARCHIVE_CDR` document and records semantic heuristics as non-human.
Unknown semantics remain `UNKNOWN`.

```text
grammar count: 0
human-certified grammar count: 0
manual geometry repair: false
```

## ADAPTATIONS

No adaptations were attempted because every source hit the extraction stop
condition.

```text
attempted: 0
generated: 0
Qwen used: false
Antigravity used: false
training run: false
```

## REAL CDR VERIFICATION

Native source-copy CDRs were opened and rendered by real Corel. No reconstructed
or adapted CDR was generated, reopened, or claimed editable.

## REVIEW ARTIFACT

No private review artifact was published because there were no passing
source/control/adaptation groups.

```text
PRIVATE_REPOSITORY: not used for this blocked pilot
WORKFLOW_RUN_ID: null
ARTIFACT_ID: null
ARTIFACT_NAME: null
aesthetic_quality: PENDING_NOT_REACHED
```

## TESTS

- Source compile: pass (`python -m compileall -q training tests`)
- Targeted tests: `18 passed`
- Full pytest: `295 passed`, 1 dependency deprecation warning
- `git diff --check`: pass

CI tests remain hermetic: they require no company CDR, Corel, GPU, Qwen, or
private review repository.

## LIMITATIONS

- The current extractor is active-page bound and has no explicit pasteboard
  artboard/cluster selection contract.
- Arbitrary curves and bitmap payloads are inspected but not reconstructable by
  the current deterministic Corel compiler.
- The selected CDRs may contain multiple production variants in one workspace;
  choosing one automatically would be a semantic assumption.
- No aesthetic conclusion can be drawn because no valid control or adaptation
  reached the review stage.

## NEXT GATE

Before repeating this pilot:

1. define a human-auditable artboard/cluster selection for pasteboard CDRs;
2. preserve arbitrary Corel curve/bitmap content through a causal structured
   representation and round-trip compiler;
3. rerun the same five IDs and require a valid control before any adaptation.

No training or new aesthetic experiment is justified by this result.

