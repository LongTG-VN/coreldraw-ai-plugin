# Training Bootstrap

This directory is intentionally separate from the CorelDRAW runtime. It prepares public/synthetic/private data for design-model research and later exposes stable inference outputs to Antigravity.

## 1. Preflight

From repository root:

```bash
python training/tools/preflight.py --write-report
python training/tools/bootstrap.py --profile smoke --apply
```

The scripts use the Python standard library and are safe to run before installing ML dependencies.

## 2. Create a dedicated environment

### Windows PowerShell

```powershell
py -3.10 -m venv .venv-training
.\.venv-training\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r training/requirements.txt
```

### Linux / WSL

```bash
python3.10 -m venv .venv-training
source .venv-training/bin/activate
python -m pip install --upgrade pip
pip install -r training/requirements.txt
```

The bootstrap requirements deliberately do not pin PyTorch/CUDA. Codex must inspect the actual GPU/driver and the selected upstream model repository before choosing a compatible PyTorch stack.

## 3. Probe public data without bulk downloading

```bash
python training/tools/probe_dataset.py --source genposter100k --limit 20
```

Or:

```bash
python training/tools/probe_dataset.py --source cgl_v2 --limit 20
```

The probe uses Hugging Face streaming and writes only a small normalized JSONL preview under `training/workspace/probes/`.

## 4. Prepare upstream research repositories

Dry-run first:

```bash
python training/tools/bootstrap.py --profile smoke --clone-upstreams
```

Actually clone shallow copies:

```bash
python training/tools/bootstrap.py --profile smoke --clone-upstreams --apply
```

Upstreams are placed in `training/vendor/` and are ignored by git.

Priority:

1. `elem2design` — layered composition/layout baseline.
2. `LLM4SVG` — editable SVG/vector path.
3. `PosterReward` — optional critic after a generator works.

## 5. Dataset gates

- smoke: maximum 500 samples.
- prototype: maximum 5,000 samples.
- research: maximum 25,000 public samples by default.
- production: only synthetic/verified-commercial/private data.

Do not jump directly to full public datasets.

## 6. License separation

Directories:

```text
training/data/research/       public research-only data
training/data/production/     production-safe data only
training/vendor/              cloned upstream repositories
training/artifacts/           checkpoints/metrics/eval outputs
training/workspace/           probes/preflight/temp state
```

Current registry lives at `training/config/datasets.json`.

`GenPoster100K` is classified research-only (`CC-BY-NC-4.0`). `CGL-Dataset-v2` is classified research-only/unverified because its current dataset card does not provide a known license.

## 7. First model experiment

Codex should not blindly execute a guessed training command. It must:

1. clone/inspect current `elem2design`;
2. inspect its current Python/CUDA/dependency requirements;
3. build a small adapter from our normalized schema;
4. create a reproducible experiment config under `training/config/experiments/`;
5. materialize <=500 research samples;
6. run a LoRA/QLoRA smoke experiment if hardware permits;
7. save metrics and qualitative outputs locally under `training/artifacts/`.

If hardware cannot train the chosen model, Codex should still finish steps 1-5 and provide a verified launch command for a suitable machine rather than pretending the run completed.

## 8. Later private data

When the private CDR archive is available, the extractor must output the same normalized schema used by public/synthetic adapters. Do not build a second training format.

Preferred future flow:

```text
CDR -> PNG + JSON + SVG/assets -> normalized design.json -> dedupe/quality -> company LoRA
```

Keep version history (`draft -> revision -> final`) when available; it is valuable preference/edit trajectory data.

## 9. Handoff to Antigravity

Training output should become a stable structured inference result. Antigravity then converts the plan into the existing Corel transaction API and iterates using preview + design checks.

See `docs/CODEX_TRAINING_PLAN.md` for the complete roadmap.

## 10. Unified structured design pipeline

The bootstrap branch now provides a source-independent editable schema under
`training/schemas/design.py`. It validates finite coordinates, absolute and
normalized bbox agreement, canvas bounds, text metadata, duplicate IDs,
hierarchy cycles, and asset references.

Build and validate the bounded GenPoster research set:

```powershell
.\.venv-training\Scripts\python.exe training\tools\build_dataset.py `
  --source genposter100k --limit 100 `
  --output training\data\research\genposter_smoke_100

.\.venv-training\Scripts\python.exe training\tools\validate_dataset.py `
  training\data\research\genposter_smoke_100 --write-report
```

The current verified gate contains 100 records split deterministically into
74 train / 8 validation / 18 test records. It remains `research_only`; one
zero-area upstream layer is dropped with explicit normalization provenance.

## 11. Elem2design adapter dry run

Convert normalized JSONL into the exact five-round/ten-message elem2design
conversation format:

```powershell
.\.venv-training\Scripts\python.exe training\tools\prepare_elem2design.py `
  training\data\research\genposter_smoke_100 `
  training\workspace\elem2design_smoke_100
```

This output is deliberately marked `training_ready: false` until four staged
render images are generated and validated for each sample. See
`docs/ELEM2DESIGN_INSPECTION.md` and
`training/config/experiments/elem2design_smoke_qlora.json`.

## 12. Baseline structured inference

The current baseline is deterministic and is **not** a trained model. It proves
the request -> design.json -> Corel transaction -> preview/metrics contract:

```powershell
.\.venv-training\Scripts\python.exe training\tools\infer_baseline.py `
  --prompt "Thiết kế poster spa cao cấp màu kem và vàng" `
  --width-mm 4000 --height-mm 1200 `
  --output training\artifacts\runs\baseline_smoke\samples\spa.design.json
```

The run writes `config.json`, `environment.json`, `dataset.json`, `metrics.json`,
the structured design, Corel operation payload, and a deterministic PNG preview.
Generated run artifacts remain ignored by Git.
