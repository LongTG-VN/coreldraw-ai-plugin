# Design AI v0.3.3 — Asset-Aware Composition Report

## RESULT

- Milestone: `Design AI v0.3.3 — Asset-Aware Composition`
- Started: `2026-08-12T08:30:52+07:00`
- Validation completed: `2026-08-12T09:20:35+07:00`
- Duration: approximately 49 minutes 43 seconds
- Replay: 5 placeholder baselines versus 5 asset-aware versions
- Fresh smoke: 5 cases × 2 newly generated candidates, no raw-output reuse
- Human preference collected: `false`
- Scorer changed: `false`

The five asset-aware replay winners are strict-schema valid, compile to Corel
operations, have no outside-canvas errors, have zero measured overlap, retain
100% text fit, and leave no editable asset placeholders. The contact sheet shows
a clear increase in realism, but not a complete solution to art direction.

## GIT

- Starting SHA: `d14d86f852cb4d6bc1fbea32985b2d3f58555e61`
- Branch: `agent/codex-training-bootstrap`
- Model retrained: `false`
- Historical v0.3.2 artifacts changed: `false`
- Downloaded binary assets committed: `false`; they remain under the ignored
  local benchmark root.

## ASSET SOURCING

The sourcing tool re-verifies Wikimedia Commons `imageinfo` extended metadata
and only accepts CC0 for public files. Search/aggregation results were not used
as provenance. All public assets point to their original file page and CC0
license. Fictional marks and the generic sale product are deterministic,
project-owned benchmark assets.

| Case | Asset | Source | License | Commercial allowed | Project-owned | SHA-256 |
|---|---|---|---|---:|---:|---|
| spa | `spa_hero_01` | [Bali Ubud spa.jpg](https://commons.wikimedia.org/wiki/File:Bali_Ubud_spa.jpg), Jeong seolah | CC0 1.0 | true | false | `5caf51b31d250b721388116d289a0670aa0a83e316f2c01a8124afba4525cd84` |
| spa | `spa_logo_01` | SPA AN NHIÊN original SVG | Project-owned | true | true | `8ff78ff5ea88321e48b45690f7e2c8a56d42a77d1d856491af1d2a2b0efa4bd0` |
| cafe | `cafe_hero_01` | [Coffee Cup on Modern Table.jpg](https://commons.wikimedia.org/wiki/File:Coffee_Cup_on_Modern_Table.jpg), Genaro35 | CC0 1.0 | true | false | `c35248ded83965ae4c0ac4b76012c78acc529d94766123cbdea25dec6c3399ed` |
| cafe | `cafe_logo_01` | MỘC CAFE original SVG | Project-owned | true | true | `0793389a39f4fd6c136d0c95ff67eb11a3677a716aae2e707fdc6641bcc9695c` |
| sale | `sale_product_01` | NOVA generic product SVG | Project-owned | true | true | `c72f6008f0367056fe2e9ee8eab97783923d40e5d6ce7780b429d8fc86d2f505` |
| sale | `sale_logo_01` | NOVA MARKET original SVG | Project-owned | true | true | `24833b90037d34b98e0dba2efd1e008483a98b3080f3e5f7e4ad924517b9687a` |
| menu | `menu_hero_01` | [Bò né.jpg](https://commons.wikimedia.org/wiki/File:B%C3%B2_n%C3%A9.jpg), Kwozyn | CC0 1.0 | true | false | `60c136928fe91c4d7b6128a7eef2365235869cf79fb193fa1837e954360eb942` |
| menu | `menu_logo_01` | BẾP NHÀ original SVG | Project-owned | true | true | `83306d0222922b7cd758a06e7400d0ec5e2791443c2d99f604f15977e3f859d7` |
| signage | `signage_logo_01` | PHỞ GIA TRUYỀN original SVG | Project-owned | true | true | `a1e4491385bcfaa9758c999fb1ba512079a8965ccfa54a9c25d100654c4ef331` |

The branded `Bottle image.jpg` candidate was rejected after visual inspection.
The CC0 `Glass bottle.jpg` candidate was not used because repeated Wikimedia
downloads returned HTTP 429. The sale benchmark therefore uses an original,
brand-neutral project asset. No ambiguous-license asset was admitted.

## CASES

### Spa

Uses a CC0 portrait wellness photograph plus an editable SPA AN NHIÊN SVG. The
engine assigns a large right-side covered hero and keeps copy on a solid left
zone. EXIF orientation is honored. This is visibly more like a presentation
draft than the old PHOTO/LOGO frame, although the art direction remains simple.

### Cafe

Uses a CC0 portrait coffee photograph plus MỘC CAFE SVG branding. Portrait
geometry drives a right-side hero, while the headline, body, and CTA stay in a
safe left copy column. This is one of the clearest realism improvements.

### Sale

Uses an original generic transparent-style product graphic and NOVA MARKET SVG.
`MEGA SALE`, `GIẢM 30%`, and `MUA NGAY` are explicitly project-created benchmark
sample data (`benchmark_sample_data: true`, `customer_provided: false`). The
product becomes the visual focal point without introducing a commercial brand.

### Menu

Uses a CC0 food image and BẾP NHÀ SVG. The image stays secondary to five aligned
rows. The five names, descriptions, and prices are explicitly synthetic
benchmark content. No phone number is invented; the CTA is `Đặt món tại quầy`.
The asset-aware menu is the only case whose existing heuristic combined score
also improves.

### Signage

Uses a project-owned PHỞ GIA TRUYỀN logo only. The brand remains contained and
uncropped on the dark signboard. It removes the placeholder but confirms that a
logo alone does less for visual quality than a strong hero/product asset.

## IMPLEMENTATION

- `AssetManifestV1` and `AssetInputV1` strictly validate role, source type,
  license flags, path containment, MIME, dimensions, aspect ratio, alpha, file
  existence, SVG safety, and SHA-256 integrity.
- Raster dimensions and rendering honor EXIF orientation.
- Deterministic analysis records dimensions, aspect ratio, alpha, brightness,
  contrast, dominant colors, and palette candidates; it makes no semantic image
  claims.
- Asset aspect ratio changes frame geometry. Explicit `contain`, `cover`,
  `fit_width`, and `fit_height` modes preserve aspect ratio and record crop and
  focal-point metadata.
- Logos default to `contain`, are not cropped, stretched, recolored, or mutated.
- Palette priority is project logo, then hero/product statistics; text contrast
  remains the overriding safety constraint.
- Text stays on a separate safe copy zone or solid surface. Typography fitting
  runs again after asset binding.
- Asset elements compile as editable frame + `import_asset` + `fit_to_frame`
  operations. Text and shapes remain separate editable elements.
- A postprocessor extension hook allows one loaded RAG/Qwen session to apply
  v0.3.2 hardening and v0.3.3 asset binding sequentially.

## REPLAY RESULTS

| Case | Placeholder combined | Asset-aware combined | Technical | Overlap | Spacing | Visual hierarchy | Text fit | Coverage | Hero area | Visual assessment |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| spa | 0.932622 | 0.876437 | 1.000000 | 0.000000 | 0.981386 | 0.574663 | 1.000000 | 0.479250 | 0.280000 | Real image is a clear realism gain; composition still restrained. |
| cafe | 0.898232 | 0.895390 | 1.000000 | 0.000000 | 0.994464 | 0.668023 | 1.000000 | 0.441300 | 0.237800 | Stronger, believable cafe draft; copy styling is still generic. |
| sale | 0.927029 | 0.910921 | 1.000000 | 0.000000 | 0.989532 | 0.755402 | 1.000000 | 0.433550 | 0.222300 | Product focus improves campaign readability; art direction remains template-like. |
| menu | 0.894145 | 0.930221 | 1.000000 | 0.000000 | 0.984173 | 0.848863 | 1.000000 | 0.425128 | 0.059400 | Most balanced objective and visible improvement; rows stay readable. |
| signage | 0.861702 | 0.832909 | 1.000000 | 0.000000 | 0.977855 | 0.559850 | 1.000000 | 0.415200 | 0.000000 | Logo removes the wireframe cue; composition still needs stronger art direction. |

Aggregate replay:

- Combined: `0.902746 → 0.889176` (`-1.5032%`)
- Technical: `0.980148 → 1.000000`
- Overlap: `0.015420 → 0.000000`
- Spacing: `0.930027 → 0.985482`
- Text fit: `1.000000 → 1.000000`
- Coverage: `0.416936 → 0.438886`
- Headline dominance: `0.807547 → 0.618444`

The unchanged heuristic does not score photographic realism. Its combined-score
drop is reported, not hidden. It primarily penalizes lower headline dominance
after real assets become focal elements. The contact sheet, not the heuristic,
is the primary artifact for the research question. No human preference has been
recorded.

Per-case comparisons are under:

`training/artifacts/benchmarks/20260812_design_v0_3_3_real_assets/runs/<case>/comparison.png`

and:

`training/artifacts/benchmarks/20260812_design_v0_3_3_real_assets/runs/<case>/comparison.html`

## FRESH SMOKE

- Model: `Qwen/Qwen3-1.7B`
- Revision: `70d244cc86ccca08cf5af4e1e306ecf908b1ad5e`
- Checkpoint: `training/artifacts/runs/20260809_qwen3_1_7b_smoke/checkpoint-5`
- Retrained: `false`
- Candidate count: `10` fresh (`5 × 2`)
- Unsafe/raw cache reuse: `0`
- Strict-schema-valid and eligible: `9/10`
- Winners produced: `5/5`
- Average candidate generation latency: `37.649235` seconds
- Peak measured VRAM: `1.551517 GiB`
- Model load duration: `4.061419` seconds

The invalid candidate was `cafe/candidate_01`: Qwen emitted invalid JSON at the
model-output stage (`Expecting value: line 67 column 13`). The second fresh cafe
candidate was valid and won. This failure is retained in the artifacts rather
than silently recovered or omitted.

## SAFETY

- Replay strict schema: `5/5`
- Replay Corel compilation: `5/5`
- Replay outside-canvas rate: `0`
- Replay overlap ratio: `0`
- Replay text fit: `1.0`
- Replay unresolved truncation: `0`
- Placeholder remaining count: `0`
- Logo aspect preservation: `1.0`
- Focal-point preservation: `1.0`
- Forbidden historical placeholder values (`0900`, `GIẢM 50`, `50%`, `39K`,
  `44K`) in final design text: none
- Sale/menu sample content: explicitly benchmark-only and not customer-provided
- Whole-design rasterization: not used

## ASSET METRICS

Replay averages:

- Asset use rate: `1.0`
- Asset intent preservation: `1.0`
- Logo aspect preservation: `1.0`
- Hero area ratio: `0.159900` across all five cases; zero-hero signage is included
- Crop ratio: `0.119803`
- Focal-point preservation: `1.0`
- Image/text contrast safety: `1.0`
- Palette/asset alignment: `1.0`
- Placeholder remaining count: `0`
- Real-asset case rate: `1.0`
- Commercial-asset case rate: `1.0`
- Missing-asset case rate: `0.0`

## CONTACT SHEET

Primary visual artifact:

`training/artifacts/benchmarks/20260812_design_v0_3_3_real_assets/contact_sheet_real_assets_5.png`

HTML index:

`training/artifacts/benchmarks/20260812_design_v0_3_3_real_assets/index.html`

The sheet uses equal-scale placeholder/asset-aware pairs and does not hide weak
cases. It is ready for human review, but no human preference is claimed.

## LICENSE MATRIX

| Layer | Commercial allowed | Reason |
|---|---:|---|
| Downloaded/project assets | true | Three verified CC0 photographs and six project-owned original graphics |
| Model checkpoint | false | Research model trained with non-commercial GenPoster-derived data |
| Reference corpus | false | Contains GenPoster CC-BY-NC-4.0-derived references |
| Final combined pipeline | false | Most restrictive upstream model/reference license governs this checkpoint |

Asset-level commercial permission does not make the model or final pipeline
commercially usable.

## BOTTLENECK DECISION

`BOTH`

Evidence for asset availability: all five cases lose the obvious placeholder
look; spa, cafe, sale, and menu gain an immediate focal object or photograph,
and menu improves its combined heuristic score while all cases improve technical
safety and spacing.

Evidence for art direction: four of five combined heuristic scores do not
improve, headline dominance falls, signage remains minimal, and the layouts are
still recognizable as deterministic templates. Real assets solve presentation
realism, not high-level composition taste.

Recommended sequence: first `v0.3.4 Visual RAG` to retrieve art-direction and
asset-placement patterns, then `v0.3.5 Vision Critic / Self-Refine` to evaluate
the rendered composition. Neither milestone was started here.

## TESTS

- `python -m compileall -q training tests`: pass
- `python -m pytest -q`: `175 passed`, one existing Starlette deprecation warning
- `git diff --check`: pass

## FINAL DECISION

- `v0.3.3_complete: true`
- `technically_safe: true`
- `asset_pipeline_ready: true`
- `real_assets_visually_improved: true`
- `ready_for_visual_rag: true`
- `ready_for_vision_critic: true`
- `ready_for_v0.4_preference_training: false`
- `production_ready: false`
- `commercial_allowed: false`

The milestone answers the research question: real assets materially improve how
close the outputs feel to usable designer drafts, but art direction remains a
co-dominant bottleneck. Completion means the bounded research pipeline and its
evidence are ready, not that the design system is production quality.

## NEXT 3 ACTIONS

1. Run a human side-by-side review of the five equal-scale comparisons and store explicit preferences.
2. Build v0.3.4 Visual RAG around licensed/private asset and composition retrieval, preserving this manifest contract.
3. After Visual RAG is measured, add v0.3.5 vision-based rendered critique and self-refinement.
