# Pasteboard-Aware Real Company Gold Pilot Report

## RESULT

```text
PASTEBOARD_REGION_REVIEW_REQUIRED
```

The active-page assumption has been removed from the candidate extraction path.
Corel source coordinates now feed deterministic `DesignRegion` analysis and a
non-destructive virtual canvas. This resolves geometry extraction for three
single-cluster sources, but it does not make their current deterministic Corel
round trip valid. Two sources contain multiple plausible regions and remain
blocked pending visual selection.

No source was certified Gold. No grammar, adaptation, or generated CDR is
claimed by this phase.

## GIT

- Branch: `codex/pasteboard-aware-gold-pilot`
- Starting SHA: `d4c04bc91491ca537d9d2e8d5577ad67fe7472bd`
- Parent checkpoint preserved: `codex/real-company-gold-pilot`

## IMPLEMENTATION

The implementation adds:

- complete object-space classification using the original Corel bottom-left
  coordinates;
- exact active-page, all-artwork-union, and deterministic spatial-cluster
  candidates;
- a strict rule that automatically selects only a single spatial cluster;
- virtual-canvas extraction that retains both source absolute geometry and
  region-relative normalized geometry;
- explicit `ACTIVE_PAGE` versus `ARTWORK_REGION` canvas provenance;
- real Corel `cdrSelection` region export without moving source objects;
- labels below, never over, region artwork;
- a bounded private human-selection package for ambiguous sources.

The clustering gap is deterministic: five percent of the source-page diagonal,
with a one-unit minimum. Top-level objects form connected components; group
children remain bound to their parent component. Cluster ordering and IDs are
stable for the same inspection evidence.

## SOURCE SAFETY

- Archive sources opened during this phase: `0`
- Source copies opened by Corel: `5`
- Source-copy `Save` calls: `0`
- Original archive size + mtime + SHA-256 verified after processing: `5/5`
- Source mutations detected: `0`
- Source objects moved: `0`
- Source pages resized: `0`

CorelDRAW `Version 22.0.0.412` exported every candidate region from source
copies by selection and closed each document without saving.

The refreshed real-Corel inspection records page, parent/group, layer, object
type, absolute bbox, visible, printable, and locked state. Availability for
visible/printable/locked metadata is `503/503` objects; all five sources expose
one inspected page layer.

## REGION ANALYSIS

| Source | Objects | Inside page | Outside page | Candidate regions | Spatial clusters | Selected region | Method | Confidence |
|---|---:|---:|---:|---:|---:|---|---|---:|
| `CDR_000159` | 24 | 0 | 24 | 2 | 1 | `cluster_001` | single spatial cluster | 0.95 |
| `CDR_000020` | 30 | 0 | 30 | 3 | 2 | none | human selection required | 0.00 |
| `CDR_000401` | 311 | 174 | 137 | 4 | 2 | none | human selection required | 0.00 |
| `CDR_000442` | 50 | 0 | 50 | 2 | 1 | `cluster_001` | single spatial cluster | 0.95 |
| `CDR_000295` | 88 | 0 | 88 | 2 | 1 | `cluster_001` | single spatial cluster | 0.95 |

`ACTIVE_PAGE_REGION` is emitted when artwork intersects the page.
`ALL_ARTWORK_REGION` is retained as context but is never treated as proof that
multiple clusters form one design.

## REGION PREVIEWS

- Candidate region previews rendered by real Corel: `13/13`
- Preview errors: `0`
- Per-source contact sheets: `5`
- Combined local contact sheet:
  `training/workspace/company_archive/pasteboard_gold_pilot/pasteboard_region_contact_sheet_all.png`

The visual evidence confirms the conservative gate:

- `CDR_000020` has a primary layout cluster and a spatially separate object;
- `CDR_000401` contains two materially different production-layout clusters;
- selecting `all_artwork` would merge competing content and is not allowed.

## VIRTUAL CANVAS EXTRACTION

For selected regions the canonical top-left bbox is derived from untouched
Corel bottom-left coordinates:

```text
virtual_left = source_left - region_left
virtual_top  = region_top - (source_bottom + source_height)
```

The source bottom-left normalized form requested by the pilot is also retained
in element provenance:

```text
x      = (source_left   - region_left)   / region_width
y      = (source_bottom - region_bottom) / region_height
width  = source_width  / region_width
height = source_height / region_height
```

The extractor never rewrites the original page dimensions. `CanvasSpec`
records the source page bounds, selected artwork-region bounds, and
normalization origin separately.

## SOURCE RESULTS

| Source | Source status | DesignDocument | Normalized geometry | Round trip | Grammar | Adaptation |
|---|---|---|---|---|---|---|
| `CDR_000159` | `ROUNDTRIP_BLOCKED` | valid, 24 objects | valid | `ROUNDTRIP_BAD` | not attempted | not attempted |
| `CDR_000020` | `REGION_SELECTION_REQUIRED` | blocked | not applicable | not attempted | not attempted | not attempted |
| `CDR_000401` | `REGION_SELECTION_REQUIRED` | blocked | not applicable | not attempted | not attempted | not attempted |
| `CDR_000442` | `ROUNDTRIP_BLOCKED` | valid, 50 objects | valid | `ROUNDTRIP_BAD` | not attempted | not attempted |
| `CDR_000295` | `ROUNDTRIP_BLOCKED` | valid, 88 objects | valid | `ROUNDTRIP_BAD` | not attempted | not attempted |

## ROUND-TRIP GATE

The three resolved sources fail before Corel reconstruction because arbitrary
Corel vectors and bitmap payloads are not supported by the current
`DesignDocument -> Corel operations` compiler.

| Source | Reconstructable objects | Rate | Blocking evidence |
|---|---:|---:|---|
| `CDR_000159` | 13 / 24 | 54.17% | unsupported vector objects |
| `CDR_000442` | 15 / 50 | 30.00% | unsupported vector objects |
| `CDR_000295` | 17 / 88 | 19.32% | unsupported vectors and bitmap payload |

Creating only supported rectangles/text would be a severely incomplete control,
so no new Corel document was created and no editability claim was made.

```text
ROUNDTRIP_GOOD: 0
ROUNDTRIP_PARTIAL: 0
ROUNDTRIP_BAD / blocked: 5
```

## GRAMMAR AND ADAPTATION

The required prerequisite is `ROUNDTRIP_GOOD`. No source reached it.

```text
Gold candidate grammars created: 0
adaptations generated: 0
generated editable CDRs: 0
Qwen used: false
Antigravity used: false
training run: false
```

Rights remain fail-closed:

```text
source_type: COMPANY_ARCHIVE_CDR
human_quality_status: GOLD_CANDIDATE_FINAL
human_certified_gold: false
rights_status: UNKNOWN
project_owned: false
commercial_allowed: false
```

## PRIVATE REGION REVIEW ARTIFACT

- Private repository: `LongTG-VN/coreldraw-ai-review-private`
- Repository visibility verified: `PRIVATE`
- Artifact: `chatgpt-pasteboard-region-selection-001`
- Workflow run ID: `32231493756`
- Artifact ID: `9357389541`
- Artifact size: `3,660,976` bytes
- Region previews: `7`
- Contact sheets: `2`
- CDR/CDT files: `0`
- SQLite files: `0`
- Absolute/local path leaks: `0`

The artifact asks only for region selection for `CDR_000020` and
`CDR_000401`. It does not reveal old/new labels, certify Gold, or select a
winner automatically.

## TESTS

- Targeted pasteboard/company tests: `31 passed`
- Full pytest: `308 passed`, one dependency deprecation warning
- Tracked Python syntax compile: `209` files passed
- `git diff --check`: passed

`python -m compileall -q .` was not used as final evidence because it traverses
the local `.venv-training`; that environment contains a PyTorch internal Python
3.12 syntax fixture while the active interpreter is Python 3.11. The final
syntax gate compiled every Git-tracked Python source in memory and excluded
virtualenv/cache files.

CI tests remain independent of Corel, company CDRs, GPU, Qwen, private assets,
and human region choices.

## LIMITATIONS

- A geometry cluster is not a semantic artboard. Human review is still required
  whenever multiple clusters exist.
- The current inspector covers the active page's available shape collection and
  retained pasteboard objects; multi-page and desktop-layer semantics remain a
  later explicit extension.
- Arbitrary Corel curves and bitmap payloads still lack a causal structured
  representation and reconstruction path.
- Region selection alone will not make the three currently resolved sources
  round-trip safe.
- No aesthetic result was measured and no human region choice is fabricated.

## NEXT GATE

1. collect explicit visual region selections for `CDR_000020` and
   `CDR_000401` from the private artifact;
2. add a causal vector/bitmap preservation strategy that can reconstruct a
   complete selected source region without flattening it;
3. rerun control reconstruction and require `ROUNDTRIP_GOOD` before extracting
   any grammar or producing two bounded adaptations.

Until both the region and reconstruction gates pass, the correct overall state
is `PASTEBOARD_REGION_REVIEW_REQUIRED`.
