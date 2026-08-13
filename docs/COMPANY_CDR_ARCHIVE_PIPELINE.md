# Company CDR Archive Pipeline

## Purpose

This pipeline inventories a company design archive without changing the source,
then supports bounded previewing, explicit human curation, Corel inspection, and
prototype conversion into `DesignDocument`. It is data infrastructure. It does
not train a model and it does not automatically declare a design Gold.

The intended flow is:

```text
immutable company archive
  -> resumable metadata inventory
  -> staged duplicate detection
  -> bounded Corel previews
  -> explicit human curation
  -> safe CDR inspection
  -> DesignDocument
  -> HUMAN_CERTIFIED_GOLD gate
  -> GoldDesignGrammarV1
```

## Non-negotiable read-only policy

The archive root and workspace must be disjoint. Source paths are resolved under
the configured archive root and symlinked directories are not traversed. Source
files are never renamed, moved, deleted, overwritten, or saved by this package.

Corel inspection follows this sequence:

1. record source size, modification time, and inode/file identifier when available;
2. open the explicitly selected CDR in CorelDRAW;
3. inspect or export a preview;
4. close the Corel document without calling `Save`;
5. verify that the source stat record is unchanged.

The CLI requires `--read-only` for every command that opens an archive source.
This is an acknowledgement, not an option to enable writes. Unit tests also
forbid fake `.cdr` byte writes inside `training/company_archive`.

## Workspace and privacy

Use an ignored local workspace outside the archive root:

```text
training/workspace/company_archive/
  archive.sqlite
  previews/
  inspections/
  extractions/
```

Absolute customer paths, filenames, previews, inspection JSON, text, and hashes
stay in the ignored workspace. Do not commit `training/workspace`, customer CDRs,
previews, or the SQLite database. The curation service binds preview reads to the
workspace preview directory and rejects path traversal.

## Inventory

Do not hard-code the archive location. For a small, user-selected directory:

```powershell
python -m training.company_archive.cli inventory `
  --root "E:\CompanyDesignArchive\ApprovedPilot" `
  --workspace "training/workspace/company_archive" `
  --read-only `
  --limit 1000
```

Omit `--limit` only after the user explicitly authorizes a larger inventory.
The current mission did not start an 800 GB scan.

The SQLite record contains:

- stable file ID, absolute and relative path, name and extension;
- size, creation time when available, and modification time;
- fast hash, SHA-256 state and SHA-256;
- CDR/PDF/image classification and work statuses;
- duplicate group and confidence;
- category and category source;
- human quality and Gold statuses;
- rights status, commercial flag, reviewer, notes;
- preview and Corel inspection metadata.

The scanner persists a deterministic relative-path cursor after every file. A
partial run resumes after that exact cursor. If the cursor no longer exists, the
scanner fails closed instead of silently skipping an unknown range. A completed
scan starts a new reconciliation scan and upserts metadata without overwriting
human curation fields.

## Staged hashing and duplicates

Hashing is intentionally staged:

- Stage A: path, size, mtime, extension. No content hash.
- Stage B: BLAKE2b fast fingerprint over file size plus bounded head/tail data,
  only for same-size duplicate candidates.
- Stage C: full streaming SHA-256 only for duplicate verification, selected
  extraction provenance, or human Gold certification.

Run duplicate grouping after inventory:

```powershell
python -m training.company_archive.cli duplicates `
  --workspace "training/workspace/company_archive"
```

A duplicate group is recorded only after SHA-256 matches. The pipeline never
deletes duplicates.

## File discovery

Priority types are `.cdr` and `.cdt`. The inventory also classifies `.pdf`,
`.svg`, `.ai`, `.eps`, `.png`, `.jpg`, `.jpeg`, `.tif`, and `.tiff`. Other
formats are retained as `OTHER`; they are not discarded.

## Bounded previews

Preview rendering is never implicit for the whole archive. Supply explicit IDs
or a bounded limit (maximum 500 per command):

```powershell
python -m training.company_archive.cli previews `
  --root "E:\CompanyDesignArchive\ApprovedPilot" `
  --workspace "training/workspace/company_archive" `
  --read-only `
  --file-id "file:..." `
  --dpi 96
```

Corel exports a PNG into the workspace and closes the source without saving.
Dimensions and render errors are persisted in SQLite.

## Human curation

Start the local-only curation UI:

```powershell
python -m training.company_archive.cli serve-curation `
  --workspace "training/workspace/company_archive" `
  --port 8005
```

Open `http://127.0.0.1:8005/curation`.

Human quality status is one of `UNREVIEWED`, `APPROVE`, `MAYBE`, or `REJECT`.
Gold status is one of `NOT_GOLD`, `GOLD_CANDIDATE`, or
`HUMAN_CERTIFIED_GOLD`. Only an explicit UI action with a reviewer identity can
create `HUMAN_CERTIFIED_GOLD`. Certification additionally requires:

- `APPROVE` human quality;
- explicitly confirmed company ownership/use rights;
- a full SHA-256 binding;
- the reviewer identity.

No heuristic, model, Antigravity agent, or Qwen output may promote Gold.
`commercial_allowed` remains false unless rights are separately and explicitly
confirmed. File presence in a company directory is not sufficient evidence.

## Safe Corel inspection

Inspect exactly one inventory record:

```powershell
python -m training.company_archive.cli inspect `
  --root "E:\CompanyDesignArchive\ApprovedPilot" `
  --workspace "training/workspace/company_archive" `
  --read-only `
  --file-id "file:..."
```

`CompanyCdrInspector` records Corel version, page size/unit, page/layer/object
counts, object tree metadata, text, font family and size, CMYK fills, groups,
bitmaps, vectors, bounding boxes, normalized bounding boxes, z-order, and layer.
It does not call source `Save`.

CorelDRAW coordinates use the document unit, while `Text.Story.Size` is retained
as typographic points. The adapter must never scale font points by inches or
millimetres.

## CDR to DesignDocument prototype

Extract one selected CDR:

```powershell
python -m training.company_archive.cli extract `
  --root "E:\CompanyDesignArchive\ApprovedPilot" `
  --workspace "training/workspace/company_archive" `
  --read-only `
  --file-id "file:..." `
  --category SALE
```

This binds a full source SHA-256 in both SQLite and the `DesignDocument`.
`--confirm-company-rights` is an explicit operator assertion; do not use it
without established policy. `--commercial-allowed` is rejected unless rights
are confirmed.

The current extractor is a page-one prototype. It preserves canvas, object type,
geometry, normalized geometry, z/layer order, text, font metadata, rotation, and
fill. Rectangle, ellipse, text, and groups can compile through the current Corel
operation compiler. Bitmap and arbitrary vector reconstruction remain marked
unsupported rather than being replaced by fake content.

## Round trip and Gold grammar

For an explicitly approved disposable copy:

```text
real Corel CDR -> CompanyCdrInspector -> DesignDocument
  -> compile_corel_operations -> Design API -> new Corel-saved CDR
```

Compare canvas, object/text counts, geometry, layer order, text, fonts, and
colors. Do not expect pixel-perfect reconstruction in this prototype. Never
save the generated result over the source archive file.

`extract_company_gold_grammar` accepts only a SHA-bound `DesignDocument` whose
inventory record is `HUMAN_CERTIFIED_GOLD`. The resulting
`GoldDesignGrammarV1` carries source file ID, source SHA-256, reviewer, rights,
and commercial status. It cannot upgrade rights.

## Scaling to the 800 GB archive

Before a large scan:

1. obtain the exact user-approved archive root and confirm the workspace is on a
   different path;
2. run a bounded inventory and preview pilot, inspect privacy exposure and disk
   capacity, then checkpoint the SQLite database;
3. scale metadata inventory first, run staged hashes only on candidates, and
   render previews only from an explicit curated queue.

Do not start the full scan from an unattended default command.

## Current evidence and limitation

The implementation was tested on temporary fixtures and a project-created CDR
that CorelDRAW 2020 saved. Real Corel inspect, no-save close, preview, extraction,
and a disposable editable CDR round trip passed. That file is not a company
archive sample and was not promoted Gold. A user-approved company CDR sample and
archive root are still required.
