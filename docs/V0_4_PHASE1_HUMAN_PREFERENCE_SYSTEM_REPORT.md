# Design AI v0.4 Phase 1 — Human Preference Collection System

## RESULT

- `start_time`: `2026-08-12T12:04:00+07:00`
- `end_time`: `2026-08-12T14:01:53+07:00`
- `duration`: approximately 1 hour 57 minutes 53 seconds of implementation, GPU generation, artifact audit, and browser verification
- `status`: `WAITING_FOR_HUMAN_REVIEW`

The local human-preference collection system is ready. It contains a strict human-only data contract, deterministic blinded queue, crash-safe sessions, FastAPI review UI, validation/export tools, a 20-brief/80-candidate initial pool, 112 review decisions, and zero fabricated human labels. No preference model was trained.

## GIT

- `starting_sha`: `acd9e95f7b77abbf17fd974d34cf90a226e772d9`
- `ending_sha`: recorded by the final Git handoff
- `remote_sha`: recorded after push
- `branch`: `agent/codex-training-bootstrap`
- `worktree`: recorded after final verification
- `commits`: implementation is committed only after full test/compile/diff verification

## REVIEW SYSTEM

- UI: `http://127.0.0.1:8002/review`
- Summary: `http://127.0.0.1:8002/review/summary`
- Server command: `python -m training.tools.human_review_server`
- API:
  - `POST /api/v1/review/session`
  - `GET /api/v1/review/next`
  - `POST /api/v1/review/submit`
  - `POST /api/v1/review/skip`
  - `GET /api/v1/review/progress`
  - `GET /api/v1/review/previous`
  - approved-root-only preview endpoint
- Keyboard shortcuts: `A`, `D`/`B`, `T`, `X`, `S`
- Resume: same reviewer and queue fingerprint reuse the persisted session, ordering, and A/B assignments after refresh/restart
- Blind review: active UI exposes only A/B, brief, category, reviewer, and progress; version/model/seed/iteration/heuristic/VLM scores are absent

Browser verification loaded the real 112-pair queue, showed two images at equal panel dimensions, reported `0 / 112`, and produced no browser console errors. The browser smoke created a session only and did not submit a preference.

## DATA CONTRACT

### `HumanReviewV1`

Stores only an explicit reviewer action with choice `a`, `b`, `tie`, or `both_bad`; optional five-dimension scores, note, confidence, reviewer/session/time, persisted blind design IDs, license, and provenance. `source` is the literal `human`, `human_verified` is the literal `true`, and provenance must say `human_ui_action`.

### `PreferencePairV1`

Contains chosen/rejected design and preview identities only when an explicit A/B human choice exists. Tie and both-bad cannot construct a synthetic winner. The export retains reviewer, optional scores, note, confidence, source review, license, and commercial state.

### `ReviewSessionV1`

Persists reviewer, queue SHA-256, deterministic seed, queue order, per-pair A/B mappings, skipped items, timestamps, and completion state. One reviewer cannot accidentally receive the same underlying queue again under a new session.

### `ReviewQueueItemV1`

Canonical pair identity uses brief ID plus the sorted content hashes. Therefore A-vs-B and B-vs-A are the same underlying pair. Queue load rejects duplicate pairs, identical artifacts, mismatched brief IDs, or permission upgrades.

## INITIAL CANDIDATE POOL

- brief count: `20`
- candidate count: `80` (`4` per brief)
- category count: `17` raw category labels, covering spa, nail, salon, cafe, milk tea, restaurant/menu, cosmetics, sale, opening, business card, signage, and social banner
- existing technically admitted Qwen candidates: `46`
- newly generated candidates selected into pool: `34`
- fresh generation attempts during Phase 1: `46`
- failed/dropped generation attempts: `12`
- unsafe reused output: `0`
- fresh generation/model runtime: `4315.35 seconds` across generation and audited retries
- peak VRAM: `1.4686 GiB`
- technical pass rate of admitted pool: `100%`
- mean selected layout distance: `0.242820`
- meaningful diversity: `18/20` briefs
- contact sheet: `training/artifacts/preference/v0_4_initial_pool/contact_sheets/initial_preference_pool_contact_sheet.png`

The requested preferred target was 30 briefs/120 candidates. Because local generation is expensive and strict safety filtering required repeated replacements, Phase 1 uses the explicitly permitted smaller gate of 20 briefs/80 candidates. It still meets the future training gate's brief/category coverage but does not meet the human-label gate.

The broad pool uses existing safe Qwen/RAG/visual-composition artifacts plus newly generated candidates. Failed v0.3.4 visual retrieval and v0.3.5 critic are disabled. The generation tool now applies deterministic v0.3.2 aesthetic hardening for future pool additions. The initial pool deliberately retains usable aesthetic negatives and does not filter by heuristic score.

Authorized real/project assets are represented by five blinded v0.3.2-vs-v0.3.3 historical comparisons. Real-asset composition is not applied to categories without a matching licensed manifest; those candidates remain an explicit limitation rather than silently using scraped imagery.

All fictional prompts are tagged `benchmark_sample_data: true` and `customer_provided: false`. Historical benchmark prices/offers remain benchmark examples and are not claimed as customer data.

## REVIEW QUEUE

- deterministic tournament pairs: `80` (`4` comparisons × `20` briefs)
- blinded historical progression pairs: `32`
- total estimated human decisions: `112`
- same-reviewer duplicate prevention: enabled
- adaptive/active learning: intentionally deferred until a reranker exists

Historical comparisons include v0.2-vs-v0.3, v0.3.1-vs-v0.3.2, five v0.3.2-vs-v0.3.3 asset cases, and the two v0.3.3-vs-v0.3.5 diagnostic cases. Their stored winners and metrics are not imported as labels.

## HUMAN LABELS

- actual human review count: `0`
- valid non-tie preference pairs: `0`
- A wins: `0`
- B wins: `0`
- ties: `0`
- both bad: `0`
- automated labels masquerading as human: `0`

The Codex browser smoke did not press any preference control. It created only the empty `Codex_UI_Smoke` session used to verify rendering and persisted blinding.

## EXPORT

Command:

```powershell
python -m training.tools.export_preferences `
  --queue training/artifacts/preference/v0_4_initial_pool/review_queue/review_queue.jsonl `
  --artifact-root training/artifacts `
  --output training/data/human_preferences/v0_4/exports/latest
```

Outputs:

- `preference_pairs.jsonl`: human-verified A/B chosen/rejected records only
- `preference_summary.json`: label/category/reviewer/license/gate statistics
- `review_validation_report.json`: identity, duplicate, path, provenance, and license validation
- `brief_split.json`: deterministic 70/15/15-oriented split by `brief_id`, never by individual pair

The zero-label export was run successfully and produced an empty JSONL plus a summary with `ready_for_preference_training=false`.

## TRAINING GATE

- valid preference pairs: `0`
- minimum required: `80` valid non-tie human pairs, `20` unique briefs, `8` categories
- preferred target: `120–200` human pairs over `30–50` briefs
- `ready_for_training`: `false`
- `preference_model_trained`: `false`

The first justified model remains a small reranker over deterministic design features. Candidate future experiments, after the gate passes, are gradient-boosted trees/small MLP, then a compact text/structure encoder, and only later a lightweight multimodal reranker. Qwen generator preference tuning is not the first step.

## TESTS

- focused v0.4 tests cover strict contracts, human-only enforcement, tie/both-bad handling, canonical identities, duplicate prevention, technical filtering, deterministic blinded sessions, completed-session reuse, submit/skip/progress/back, path containment/traversal, exporter validation, benchmark provenance, and brief-level splits
- `pytest`: `209 passed`, one existing Starlette/httpx deprecation warning
- `compile`: `python -m compileall -q training tests` passed
- `git diff --check`: passed
- GitHub CI: checked after push; CI must not download Qwen, require GPU, generate the pool, or require human reviews

## LICENSE

| Layer | State |
|---|---|
| Candidate assets | Mixed verified CC0/project-owned where v0.3.3 manifests exist; placeholder/project benchmark content elsewhere |
| Reference corpus | research-only; includes GenPoster CC-BY-NC-4.0-derived records |
| Qwen planner checkpoint | research-only because training data is GenPoster-derived |
| Human preference records | no license upgrade; inherit the most restrictive candidate/source state |
| Final commercial status | `commercial_allowed=false` |

Human authorship of a preference label does not make its underlying model output/reference lineage commercial-safe.

## LIMITATIONS

- The pool contains 20 briefs rather than the preferred 30 because 46 fresh attempts plus strict replacements already consumed about 72 minutes of measured model runtime.
- Two briefs have low structural diversity; this is reported, not hidden.
- Not every category has a legally cleared real-asset manifest, so real assets are concentrated in five historical comparisons.
- The current previews still expose the known v0.3.x template/wireframe aesthetic; that is useful preference signal but not production quality.
- One reviewer per pair is allowed in Phase 1; multi-reviewer agreement is deferred.
- Skipped pairs remain skipped within that session; a future queue-management UI may allow explicit unskip.
- No authentication is provided; the server is intentionally local-only.

## FINAL DECISION

- `v0.3.3_stable`: true
- `v0.3.4_failed_experiment_preserved`: true
- `v0.3.5_failed_experiment_preserved`: true
- `preference_collection_ready`: true
- `review_ui_ready`: true
- `initial_candidate_pool_ready`: true
- `human_labels_collected`: 0
- `ready_for_preference_training`: false
- `preference_model_trained`: false
- `v0.4_complete`: false
- `production_ready`: false
- `commercial_allowed`: false

## WHAT USER MUST DO NEXT

Run:

```powershell
python -m training.tools.human_review_server
```

Open:

```text
http://127.0.0.1:8002/review
```

Enter a reviewer name and click the prettier design. No JSON editing or model loading is required during review.

## NEXT 3 ACTIONS

1. Collect at least 80 real non-tie human decisions through the local UI, preferably completing all 112 queued comparisons.
2. Run `training.tools.export_preferences` and inspect the validation/statistics report for reviewer duplicates, category coverage, and the training gate.
3. Only after the gate passes, train and independently evaluate a small structured-feature preference reranker before considering generator tuning.
