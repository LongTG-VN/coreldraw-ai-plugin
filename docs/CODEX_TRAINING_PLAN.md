# Codex Training Plan — Design AI Bootstrap

## Goal

Build the training system before the private CorelDRAW archive is ready. Public data is used only to prove architecture and learn generic design/layout behavior; production quality and company style will later come from synthetic/verified-commercial/private data.

Target runtime:

```text
request
  -> design model
  -> normalized design plan / SVG
  -> Antigravity
  -> /api/v1/design/transaction
  -> CorelDRAW
  -> preview/check/refine
  -> editable CDR + PDF
```

## Non-goals for bootstrap

- Do not download all public datasets.
- Do not full-fine-tune a large model before the smoke gate works.
- Do not mix research-only data into a production checkpoint.
- Do not replace the existing Corel runtime with model-specific code.
- Do not wait for the private 800 GB archive before validating the pipeline.

## Public sources

### GenPoster100K

- Hugging Face id: `creative-graphic-design/GenPoster100K`
- Current card: ~102,703 rows, ~488 GB total.
- Useful fields: poster/background image, layer text, bbox, font, font size, tracking, justification, color, class label, layer image.
- Current license: `CC-BY-NC-4.0`.
- Project classification: **research only**.

### CGL-Dataset-v2

- Hugging Face id: `creative-graphic-design/CGL-Dataset-v2`
- Current card: ~60.5k train rows plus test data.
- Useful fields: poster image, layout annotations, text annotations/features.
- Current card license: `unknown`.
- Project classification: **research only until rights are verified**.

### Synthetic data

Synthetic data created by our own system is the preferred bridge toward production training. Every generated sample should retain:

- prompt / customer intent;
- generated structured plan;
- rendered preview;
- deterministic Corel check results;
- visual critic score when available;
- accepted/rejected relationship for preference training;
- model/config provenance.

## Upstream model repositories

Bootstrap around these repositories rather than copying their source into this project:

1. `https://github.com/microsoft/elem2design.git`
   - layered composition / layout planning;
   - preferred first generator baseline.
2. `https://github.com/ximinng/LLM4SVG.git`
   - SVG understanding/generation;
   - preferred editable-vector research path.
3. `https://github.com/MeiGen-AI/PosterReward.git`
   - optional critic/reward path after generation works.

Clone them under `training/vendor/` and keep them out of git.

## Unified dataset contract

All adapters should converge on a stable JSON-compatible schema. Exact implementation can evolve, but preserve these concepts:

```json
{
  "schema_version": "0.1",
  "sample_id": "source:123",
  "source": {
    "name": "genposter100k",
    "split": "train",
    "license_class": "research_only",
    "upstream_id": "123"
  },
  "canvas": {
    "width": 1080,
    "height": 1350
  },
  "category": "poster",
  "elements": [
    {
      "id": "title_1",
      "type": "text",
      "bbox_norm": [0.1, 0.08, 0.8, 0.18],
      "z_index": 4,
      "text": "OPENING SOON",
      "font": "Example Font",
      "font_size": 72,
      "color": [0, 0, 0, 1],
      "asset_ref": null
    }
  ]
}
```

Rules:

- Normalize bboxes to `[0,1]` relative to canvas.
- Keep original dimensions as metadata.
- Never discard upstream ids/license information.
- Preserve unknown values as null rather than inventing them.
- Keep research and production samples physically separated.

## Phase 0 — Environment preflight

Codex runs:

```bash
python training/tools/preflight.py --write-report
python training/tools/bootstrap.py --profile smoke --apply
```

Collect:

- Python version;
- git availability;
- free disk;
- NVIDIA GPU names / VRAM if available;
- CUDA visibility via `nvidia-smi`;
- workspace paths.

Output: `training/workspace/preflight.json` (ignored by git).

No CUDA is acceptable for this phase.

## Phase 1 — Dataset smoke ingestion

Install bootstrap dependencies in a separate environment and run:

```bash
python training/tools/probe_dataset.py --source genposter100k --limit 20
```

Acceptance criteria:

- streaming works;
- no full dataset download is triggered;
- sample metadata can be normalized;
- source/license metadata survives normalization;
- malformed rows are reported, not silently skipped.

Then implement a real adapter that can materialize <=500 training samples with only the assets required by the chosen baseline.

## Phase 2 — Layout model smoke training

Primary baseline: `microsoft/elem2design` ideas/code.

Codex should inspect the current upstream README/install scripts first, then create a reproducible experiment wrapper under this repo instead of editing vendor code blindly.

Smoke target:

- <=500 normalized samples;
- LoRA/QLoRA where supported;
- one train config checked into `training/config/experiments/`;
- one command to train;
- one command to infer;
- machine-readable eval output;
- qualitative preview grid or sample folder.

A smoke run is successful because the complete loop works, not because visual quality is high.

## Phase 3 — Prototype layout model

Scale to <=5,000 samples only after Phase 2 is reproducible.

Measure at minimum:

- bbox validity rate;
- out-of-canvas rate;
- element overlap statistics;
- text/layout constraint adherence;
- qualitative human review of a fixed prompt set.

Keep baseline and trained outputs on the same fixed eval prompts.

## Phase 4 — Vector model

Use `LLM4SVG` as the first research path.

Goals:

- prompt/design-plan -> valid SVG;
- SVG imports into CorelDRAW;
- dimensions and viewBox are sane;
- no external network references in generated SVG;
- round-trip preview can be rendered and inspected.

Start with upstream checkpoints/datasets where allowed for research. Build our own production-safe vector preference data later.

## Phase 5 — Critic / reward

Only after at least one generator is working.

Research path:

- evaluate `PosterReward` or a comparable visual critic;
- combine with deterministic Corel checks;
- never let a learned critic replace hard print constraints.

Desired score contract:

```text
visual_quality
layout_hierarchy
typography
prompt_fidelity
brand/style consistency
print_readiness
```

`print_readiness` remains rule-based where possible.

## Phase 6 — Synthetic factory

Generate multiple candidates per prompt:

```text
prompt -> N plans -> Corel render -> deterministic checks -> visual critic -> rank
```

Persist chosen/rejected pairs for preference optimization. Use a fixed seed/eval set so improvements are measurable.

Preferred production bootstrap data:

- prompts written/generated by us;
- assets with clear usage rights;
- layouts/plans generated by our own pipeline;
- edits accepted by a human designer.

## Phase 7 — Private 800 GB Corel archive

When available, do not invent a new format. Build a CDR extractor that maps into the same normalized schema.

Expected private pipeline:

```text
CDR
 -> preview PNG
 -> objects/layers JSON
 -> SVG/assets where practical
 -> normalized design.json
 -> quality filter/dedup
 -> train/val/test split
 -> company-style LoRA
```

Important split rule: avoid near-duplicate customer/project versions leaking between train and validation/test.

If version history exists (`v1 -> v2 -> final`), preserve it as edit/preference trajectories instead of flattening everything into independent samples.

## Resource policy

Codex should adapt to actual hardware:

- No/weak GPU: preprocessing, evaluation, dataset schemas, inference contracts, tiny CPU tests.
- Consumer GPU: QLoRA/LoRA, small batches, gradient accumulation/checkpointing.
- Large GPU/cloud: scale only after local smoke/prototype metrics justify it.

Never select a CUDA/PyTorch stack by guess. Inspect GPU driver plus current upstream requirements first.

## Experiment bookkeeping

Every actual training run should create a local run directory such as:

```text
training/artifacts/runs/2026-08-09_elem2design_smoke/
  run.json
  config.json
  metrics.json
  samples/
  adapter/
```

`run.json` should contain git commit, dataset source/version, license class, sample count, base model, dependency versions, GPU info, seed, command, start/end status, and output paths.

Never commit large run artifacts.

## Handoff to Antigravity

The design model should expose a stable structured output before Antigravity is involved. Antigravity should not have to understand training-framework internals.

Preferred contract:

```json
{
  "canvas": {"width_mm": 4000, "height_mm": 1200},
  "operations": [
    {"op": "create_rectangle", "name": "background"},
    {"op": "create_text", "name": "headline", "text": "..."},
    {"op": "align", "shape_names": ["headline"], "relative_to": "page"}
  ]
}
```

Antigravity converts/validates this into the existing transaction endpoint and performs the visual feedback loop.

## Immediate Codex backlog after checkout

1. Run preflight and smoke bootstrap.
2. Install bootstrap dataset dependencies.
3. Probe GenPoster100K via streaming.
4. Implement normalized GenPoster adapter + schema tests.
5. Materialize a <=500-sample research set.
6. Clone/inspect `elem2design`; document exact compatible environment.
7. Build first smoke training wrapper/config.
8. Run a tiny training/eval if hardware permits; otherwise leave a verified command and test fixtures.
9. Add fixed evaluation prompts and metrics.
10. Only then consider 5k samples, LLM4SVG, or a visual reward model.

## Verified bootstrap checkpoint — 2026-08-09

- Hardware preflight records 20 logical CPU cores, 31.63GB RAM, RTX 3060 Laptop
  6GB, driver-reported CUDA 13.1, no `nvcc`, and 52.26GB free disk.
- GenPoster streaming probe succeeds for 20 rows without bulk download.
- Unified design schema, GenPoster adapter, validation, deterministic splitting,
  and license lineage are implemented.
- A 100-record research-only smoke set validates with zero schema issues:
  74 train / 8 validation / 18 test.
- Elem2design layout format dry-run succeeds for all 100 records but is not
  training-ready because staged render images are not yet available.
- Deterministic baseline inference produces valid `design.json`, Corel
  transaction operations, PNG preview, and machine-readable layout metrics.
- No model training/checkpoint is claimed: the inspected 8B multimodal recipe
  exceeds the local 6GB VRAM gate.

## Verified Design AI v0.1 checkpoint — 2026-08-09

- Elem2Design remains intact as a research/reference integration.
- `Qwen/Qwen3-1.7B` revision
  `70d244cc86ccca08cf5af4e1e306ecf908b1ad5e` trains locally with NF4 QLoRA.
- The measured 100-record SFT gate uses sequence length 1664 and retains all
  74 train records without truncating JSON targets.
- Five real optimizer steps completed at batch 1 / accumulation 4, peak PyTorch
  VRAM 5.228 GiB, and final train loss 1.12279.
- The saved adapter reloads in a separate process and produces a structured
  layout that validates after explicit logged shorthand recovery, compiles to
  Corel operations, renders, and receives deterministic layout metrics.
- Raw output does not yet match the unified schema directly. Do not scale to
  500 records until direct schema adherence improves.
- The checkpoint remains research-only because its SFT data is derived from
  GenPoster100K CC-BY-NC-4.0.
