# Design AI v0.1 — Local Structured Planner

## Pinned model and stack

- Model: `Qwen/Qwen3-1.7B`
- Revision: `70d244cc86ccca08cf5af4e1e306ecf908b1ad5e`
- Model license: Apache-2.0
- Training-data license: GenPoster100K CC-BY-NC-4.0 (`research_only`)
- PyTorch: `2.12.1+cu126`
- Transformers: `5.14.1`
- PEFT: `0.20.0`
- Accelerate: `1.14.0`
- bitsandbytes: `0.50.0`

Primary references:

- https://huggingface.co/Qwen/Qwen3-1.7B
- https://huggingface.co/Qwen/Qwen3-1.7B/commit/70d244cc86ccca08cf5af4e1e306ecf908b1ad5e
- https://qwen.readthedocs.io/en/latest/getting_started/quickstart.html
- https://huggingface.co/docs/bitsandbytes/main/en/reference/nn/linear4bit
- https://pytorch.org/get-started/previous-versions/

Qwen3 needs Transformers 4.51 or newer. This run uses non-thinking chat
templates because the target is compact JSON rather than chain-of-thought.

## Dataset projection

The adapter in `training/adapters/qwen3_sft.py` receives validated unified
`DesignDocument` objects. It keeps the research provenance, selects a bounded
editable subset, adds an explicit background, and converts unavailable image
layers to rectangle placeholders. Every assistant target is round-trip
validated before tokenization.

The 100 source records remain split 74 train / 8 validation / 18 test. With a
four-element cap, measured Qwen3 chat lengths are:

```text
min 566, p50 1112, p90 1329, p95 1472, p99 1565, max 1611
```

The configured sequence length is therefore 1664, not the model's 32768-token
maximum. No records were rejected by the training collator.

## Reproduce the local checkpoint

Install CUDA PyTorch separately, then the isolated planner stack:

```powershell
.\.venv-training\Scripts\python.exe -m pip install torch==2.12.1 `
  --index-url https://download.pytorch.org/whl/cu126
.\.venv-training\Scripts\python.exe -m pip install `
  -r training\requirements-qwen3.txt
```

Prepare and measure the SFT data:

```powershell
.\.venv-training\Scripts\python.exe training\tools\prepare_qwen3_sft.py `
  --input training\data\research\genposter_smoke_100 `
  --output training\data\research\genposter_smoke_100_qwen3_sft `
  --max-elements 4
```

Run the five-step QLoRA smoke experiment:

```powershell
.\.venv-training\Scripts\python.exe training\tools\train_qwen3_planner.py `
  --config training\config\experiments\qwen3_1_7b_local_qlora.json `
  --dataset training\data\research\genposter_smoke_100_qwen3_sft `
  --output training\artifacts\runs\20260809_qwen3_1_7b_smoke
```

The run uses NF4 double quantization with FP16 compute, LoRA rank 8 / alpha
16 on `q_proj` and `v_proj`, batch size 1, gradient accumulation 4, and
gradient checkpointing. It produced a real 6.14 MB adapter checkpoint after
five optimizer steps.

## Reloaded inference gate

```powershell
.\.venv-training\Scripts\python.exe training\tools\infer_qwen3_planner.py `
  --checkpoint training\artifacts\runs\20260809_qwen3_1_7b_smoke\checkpoint-5 `
  --config training\config\experiments\qwen3_1_7b_local_qlora.json `
  --prompt "Thiết kế poster spa cao cấp màu kem và vàng" `
  --width-mm 4000 --height-mm 1200 --max-new-tokens 1664 `
  --output training\artifacts\runs\20260809_qwen3_1_7b_smoke\samples\spa
```

The checkpoint reload and generation are real. The five-step adapter still
emits a valid JSON shorthand instead of the exact unified schema. The parser
therefore logs `raw_schema_valid: false`, rejects remote image URLs, converts
the shorthand into safe editable primitives, and reruns the strict unified
validator. The resulting `design.json` has `trained_model: true` and compiles
to the existing Corel transaction operations.

This limitation blocks the 500-sample gate for now. A follow-up should improve
direct schema adherence before increasing data volume.
