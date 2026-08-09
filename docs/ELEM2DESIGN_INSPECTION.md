# Elem2design / LaDeCo Inspection

Inspected shallow upstream commit: `4665358` under
`training/vendor/elem2design`. Vendor source is ignored by this repository.

## License and architecture

- Repository code: MIT.
- Base language model: `meta-llama/Llama-3.1-8B` (license must be accepted and
  evaluated separately).
- Vision tower: `openai/clip-vit-large-patch14-336`.
- Model flow: layer planning followed by LLaVA-style iterative layered
  composition across background, underlay, logo/image, text, and embellishment.
- Published adapter/checkpoint: `microsoft/elem2design` (model card terms apply
  separately from repository code).

## Real data contract

`dataset/src/crello/create_dataset.py` emits a JSON array. Each sample contains:

```text
id
image[]
conversations[10]  # alternating human/gpt, five design layers
render_image[]
render_text[]
```

Each predicted element follows the upstream default schema:

```text
index, left, top, width, height, angle,
font, font_size, color, text_align,
capitalize, letter_spacing, line_height, text
```

The local adapter is `training/adapters/elem2design.py`. It can validate the
layout conversation contract now. It does not claim training readiness until
each sample has four intermediate rendered images corresponding to the four
`<image>` turns.

## Upstream commands

Training is routed through `scripts/finetune_lora.sh` to
`llava/train/train_mem.py`. The upstream shell wrapper enables LoRA but leaves
`bits=16`; QLoRA exists in `llava/train/train.py` and requires explicit
`--bits 4 --double_quant True --quant_type nf4`.

Inference entrypoint:

```text
python llava/infer/infer.py \
  --model_name_or_path <adapter> \
  --data_path <test.json> \
  --image_folder <images> \
  --output_dir <output> \
  --start_layer_index 0 \
  --end_layer_index 4
```

## Environment and hardware decision

Upstream recommends Python 3.10 and pins Torch 2.7.0, torchvision 0.22.0,
Transformers 4.44.2, DeepSpeed 0.14.4, bitsandbytes, and flash-attn. CUDA is not
pinned by the upstream project.

The inspected local machine has an RTX 3060 Laptop GPU with 6GB VRAM. The 8B
multimodal model, CLIP tower, LoRA activations, and upstream 15k sequence recipe
do not fit this verified budget. No training or checkpoint is claimed. The
prepared research config lowers QLoRA rank and sequence length, but is marked
`local_execution_supported: false`; it is intended for a suitable Linux/CUDA
machine after staged render data is ready.

## Deferred upstreams

- LLM4SVG repository code is MIT, but its model/dataset licenses remain
  separate. Its main 7B VLM path exceeds the current 6GB gate.
- PosterReward has no root license file at the inspected revision. Its 8B Qwen
  VLM stack is deferred and must not be treated as production-safe without a
  license decision.
