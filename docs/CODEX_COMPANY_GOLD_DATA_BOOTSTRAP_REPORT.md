# Codex Company Gold Data Bootstrap Report

## RESULT

```text
start_time: NOT_MACHINE_RECORDED (audit began before the recorded Corel smoke)
recorded_corel_smoke_start: 2026-08-13T13:00:14.739959+07:00
end_time: 2026-08-13T13:30:56.1693894+07:00
final_status: WAITING_FOR_COMPANY_CDR_SAMPLE
```

The stabilized baseline, real Corel runtime, and a bounded company-archive data
pipeline are verified. No model was trained and the 800 GB archive was not
scanned. The live data smoke used a project-created Corel document and therefore
does not satisfy the company-owned Gold sample gate.

## GIT

```text
starting_branch: stabilize/pre-codex-return-20260812
starting_sha: abe283b5281551d487cd3b85b1bf85ba26de17ac
implementation_branch: codex/company-gold-data-bootstrap
implementation_sha: 58cc50356d67c0fafa60548d5de65d5b81824578
final_sha: recorded after the documentation commit in the final handoff message
remote_sha: PENDING_PUSH
worktree: documentation changes only at report capture; final clean gate pending commit
```

The stabilization branch was not rewritten. Ignored artifacts, checkpoints,
human review data, downloaded assets, and workspaces were preserved.

## STABILIZATION AUDIT

Draft PR #5 was open and cleanly mergeable at audit time. Its stabilization head
matched `abe283b5281551d487cd3b85b1bf85ba26de17ac`. The audit confirmed:

- provenance defaults fail closed;
- GenPoster stays CC-BY-NC-4.0, non-commercial, and not project-owned;
- fake `.cdr` generation is rejected;
- manual Gold fixtures are quarantined as regression data;
- deterministic planner output and nonce echo cannot prove external AI execution;
- approved source manifests and real planner evidence are required;
- CI fixtures are hermetic;
- failed v0.3.4/v0.3.5 research remains frozen.

Before implementation, source-only compile, `git diff --check`, and all 272
baseline tests passed. Full-root compile encountered only the known Python 3.12
syntax inside the local `.venv-training` while the active interpreter was Python
3.11; source-only compile was used rather than treating a dependency file as
project source.

## CORELRUNTIME

Conclusion: `REAL_COREL_RUNTIME_VERIFIED`.

```text
Corel version: Version 22.0.0.412
Python: 3.11.9
API: http://127.0.0.1:8001
real CDR: training/artifacts/corel_smoke/codex_resume_real_corel/codex_resume_editable_mm.cdr
CDR size: 587158 bytes
source SHA256: b26d2d22f3943d263960c9bfd32651d61d0132434f42314c73bad5e20c3721fb
object count before save: 3
object count after reopen: 3
editable text verified: true
editable vector verified: true
PNG export verified: true
PDF export verified: true
rollback verified: true
```

Snapshot, text/rectangle/ellipse creation, transform, typography, fill, committed
transaction, intentional failed transaction, rollback, Corel `SaveAs`, close,
reopen, post-reopen text/vector mutation, current save, PNG, and PDF all passed.
The CDR was saved by Corel itself. The smoke artifact is ignored and not
committed.

The live audit also corrected a real unit bug: Corel enum `cdrMillimeter` is `3`,
not `4` (`4` is centimetres). A regression test now enforces this.

## ARCHIVE INVENTORY

`training.company_archive` adds:

- strict Pydantic inventory/inspection contracts;
- disjoint root/workspace and source containment checks;
- deterministic, resumable metadata scanning;
- SQLite persistence with scan cursor and curation event history;
- CDR/CDT, PDF, image/vector, and other classification;
- statistics for counts, bytes, date range, and largest files;
- CLI operations that require an explicit archive root and `--read-only`.

The only live inventory smoke used the project-owned Corel smoke directory:

```text
files: 16
bytes: 3,686,288
CDR/CDT: 4
PDF: 2
images: 2
```

Those counts are an implementation smoke, not company archive statistics. The
800 GB archive scan was not started.

## READ-ONLY GUARANTEES

- Archive and workspace must be disjoint.
- Resolved sources must remain beneath the approved root.
- Directory symlinks are not traversed.
- Source size/mtime/file identity are checked before and after hash, inspect, and
  preview operations.
- Corel source documents are closed without calling `Save`.
- Preview output is restricted to the ignored workspace.
- No company archive module writes bytes to a `.cdr` file.
- Existing source files are never renamed, moved, deleted, or overwritten.

The real smoke source retained the same 587,158-byte size, mtime, and SHA-256
after inspect, preview, and extraction.

## HASHING

Stage A records path, size, mtime, and type only. Stage B computes a bounded
BLAKE2b head/tail fingerprint only for same-size candidates. Stage C computes a
streaming full SHA-256 only for duplicate verification, extraction provenance,
or human Gold certification. Extraction persists the bound SHA-256 back to
SQLite and verifies it matches the `DesignDocument` source ID.

## DUPLICATES

Duplicate candidates are grouped first by size and fast fingerprint, then
verified by SHA-256. Only verified matches receive a duplicate group ID and
`SHA256_VERIFIED` confidence. No deletion or archive cleanup is implemented.

The fixture suite verifies duplicate detection and false-positive separation.
The small live smoke contained no SHA-verified duplicate group.

## PREVIEWS

`PreviewBatcher` requires explicit file IDs or a bounded limit of 1–500. It uses
Corel to export PNG into the ignored workspace and persists dimensions/status or
the exact error. It never renders the entire archive implicitly.

The selected project CDR rendered successfully to:

```text
training/workspace/company_archive_smoke/previews/baad06dd8619e8cab662e12601d63482.png
```

## HUMAN GOLD CURATION

The local curation UI exposes only `APPROVE`, `MAYBE`, and `REJECT`, optional
category, notes, rights confirmation, and Gold certification. Gold promotion is
accepted only from an explicit `human_ui_action` with reviewer identity.

`HUMAN_CERTIFIED_GOLD` additionally requires `APPROVE`, confirmed company
rights, and full SHA-256. Automated/heuristic promotion is rejected. `both_bad`
or preference data is not synthesized. Commercial permission remains false
unless separately confirmed.

Launch command:

```powershell
python -m training.company_archive.cli serve-curation `
  --workspace training/workspace/company_archive `
  --port 8005
```

## CDR INSPECTOR

`CompanyCdrInspector` opens one selected `.cdr`/`.cdt`, resolves the real Corel
`ActiveDocument`, inspects it within the COM apartment, closes without save, and
checks source invariants. It extracts page dimensions/unit, layers, object tree,
types, bounding boxes, normalized boxes, z-order, text, font metadata, CMYK
fills, groups, vectors, and bitmaps.

Real inspection of the project smoke CDR found one page, two layers, three
editable objects, one text object, two vector objects, and Arial. Corel reopened
the file using inch page units; geometry was correctly converted to millimetres
while font size stayed in points.

## CDR → DESIGNDOCUMENT

The page-one prototype binds a full source SHA-256 and produces a strict
`DesignDocument`. The real smoke produced:

```text
schema valid: true
elements: 3
current compiler complete: true
compiled Corel operations: 5
company_sample_human_approved: false
```

Text, rectangle, ellipse, geometry, normalized geometry, rotation, layer/z-order,
font, and CMYK fill were preserved. Bitmap and arbitrary vector reconstruction
are marked unsupported rather than silently replaced.

## ROUND TRIP

A disposable project smoke round trip passed:

```text
Corel-saved source CDR
  -> inspect
  -> DesignDocument
  -> five deterministic Corel operations
  -> Design API transaction
  -> new Corel SaveAs CDR
  -> close/reopen
  -> three separate editable objects
```

The reopened result retained editable Arial 32pt text, a rectangle, and an
ellipse. Rotation changes axis-aligned bounding dimensions, so this prototype is
not claimed pixel-perfect. This evidence validates the mechanism only. It is not
a user-approved company CDR round trip.

## GOLD GRAMMAR INTEGRATION

`extract_company_gold_grammar` accepts only a human-certified, SHA-bound company
inventory record whose provenance matches the `DesignDocument`. It records
source type, file ID, SHA-256, reviewer, rights, project ownership, and commercial
status. Unit tests verify fail-closed rights and no automatic Gold promotion.

No company Gold grammar was created because no user-approved company sample was
provided.

## TESTS

```text
baseline before changes: 272 passed
latest local pytest: 285 passed, 1 dependency deprecation warning
source-only compileall: PASS
git diff --check: PASS
```

The new tests cover path safety, source immutability, resumable scan, SQLite,
classification, staged hashes, duplicates, human certification, rights,
previews, path traversal, fake Corel no-save behavior, normalized extraction,
font units, compiler compatibility, Gold provenance, and fake CDR prevention.

## CI

```text
Python 3.10: PENDING_PUSH
Python 3.11: PENDING_PUSH
Python 3.12: PENDING_PUSH
```

CI does not require Corel, CUDA, Qwen, private files, or the archive. The real
Corel integration smoke remains local-only.

## LIMITATIONS

- No company archive root or company CDR sample was supplied.
- The full 800 GB archive has not been scanned.
- Extraction currently covers the active/first page prototype.
- Bitmap and arbitrary vector reconstruction are not complete.
- Semantic design roles are not inferred from company objects yet.
- Round-trip geometry is structural, not pixel-perfect.
- Rights and commercial permission still require explicit human/project policy.
- No model was trained and no aesthetic-quality claim is made.

## NEXT 3 ACTIONS

1. Provide one explicitly approved company-owned CDR **copy** and its archive
   root/rights decision for a real company extraction and round-trip gate.
2. Run a bounded read-only inventory plus preview pilot on a small user-selected
   folder, review the SQLite/privacy output, and human-curate initial Gold
   candidates.
3. After the pilot passes, extend extraction to multi-page/group/bitmap/vector
   fidelity before authorizing any larger archive scan.

## FINAL STATUS

```text
WAITING_FOR_COMPANY_CDR_SAMPLE
```
