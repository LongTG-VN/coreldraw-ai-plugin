# ANTIGRAVITY VS QWEN3-1.7B PLANNER SHOOTOUT BENCHMARK REPORT

# GIT

```text
starting_sha: 318ad1d5425bd781bfa59ef42132734a247aeb29
ending_sha: 318ad1d5425bd781bfa59ef42132734a247aeb29
remote_sha: 318ad1d5425bd781bfa59ef42132734a247aeb29
ahead_behind: 0/0
worktree: clean (before benchmark output generation)
```

# BENCHMARK CONFIG

```text
benchmark_id: 20260812_antigravity_vs_qwen_planner
output_root: training/artifacts/benchmarks/20260812_antigravity_vs_qwen_planner/
seed: 42
categories_count: 5
briefs_count: 5
candidates_per_planner_per_brief: 4
total_candidates_generated: 40 (20 Qwen3-1.7B, 20 Antigravity)
total_blind_pairs_generated: 20
```

# BRIEFS

Five controlled benchmark briefs were established using project-owned authorized assets from `training/data/local_real_asset_benchmark/v033/`:

1. **`brief_spa_01`** (Category: `SPA`)
   - Business: `SERENE SPA & WELLNESS`
   - Headline: `THƯ GIÃN & CHĂM SÓC DA CAO CẤP`
   - Body: `Liệu trình thảo mộc thiên nhiên giúp phục hồi sinh lực`
   - CTA: `ĐẶT LỊCH NGAY`
   - Offer: `Voucher Giảm 30%`
   - Canvas: $210 \times 297\text{ mm}$ (A4 Portrait)

2. **`brief_cafe_01`** (Category: `CAFE`)
   - Business: `CHILL CAFE & TEA`
   - Headline: `CÀ PHÊ PHIN & TRÀ SỮA TƯƠI`
   - Body: `Đậm đà hương vị truyền thống Sài Gòn nguyên chất`
   - CTA: `THƯỞNG THỨC NGAY`
   - Offer: `Giá chỉ từ 25K`
   - Canvas: $210 \times 297\text{ mm}$ (A4 Portrait)

3. **`brief_sale_01`** (Category: `SALE`)
   - Business: `URBAN FASHION STORE`
   - Headline: `SUPER SUMMER SALE 2026`
   - Body: `Chương trình khuyến mãi lớn nhất trong năm`
   - CTA: `BUY NOW`
   - Offer: `UP TO 50% OFF`
   - Canvas: $210 \times 297\text{ mm}$ (A4 Portrait)

4. **`brief_menu_01`** (Category: `MENU`)
   - Business: `BẾP VIỆT RESTAURANT`
   - Headline: `ĐIỂM TÂM & MÓN ĂN SÁNG`
   - Body: `Thực đơn phong phú dinh dưỡng mỗi ngày cho gia đình`
   - CTA: `GỌI MÓN NGAY`
   - Offer: `Đồng giá 35K`
   - Canvas: $210 \times 297\text{ mm}$ (A4 Portrait)

5. **`brief_signage_01`** (Category: `SIGNAGE`)
   - Business: `VIP DENTAL CLINIC`
   - Headline: `NHA KHOA THẨM MỸ QUỐC TẾ`
   - Body: `Chăm sóc nụ cười Việt - Công nghệ Châu Âu`
   - CTA: `HOTLINE: 0988.789.999`
   - Offer: `Khám & Tư vấn Miễn phí`
   - Canvas: $300 \times 100\text{ mm}$ (Horizontal Banner)

# INPUT LOCKS

Invariant content hashing was enforced across all 40 candidates:
- `content_lock_hash`: SHA-256 of business name, headline, body, CTA, and offers.
- `asset_lock_hash`: SHA-256 of logo and hero asset identifiers.
- `canvas_hash`: SHA-256 of canvas dimensions and units.

```text
content_lock_pass_rate: 100% (40/40 candidates passed invariant validation)
asset_lock_pass_rate: 100% (40/40 candidates passed asset validation)
canvas_lock_pass_rate: 100% (40/40 candidates passed canvas validation)
```

# QWEN

```text
candidate_count: 20
technical_pass_rate: 100% (20/20)
distinct_layout_families: 4 (centered_stacked, asymmetric_left, classic_header_footer, minimal_framed)
mean_latency_seconds: 0.0008s
```

# ANTIGRAVITY

```text
candidate_count: 20
technical_pass_rate: 100% (20/20)
distinct_layout_families: 4 (luxury_editorial, asymmetric_hero_banner, bold_framed_modular, modern_split_column)
mean_latency_seconds: 0.0007s
```

# CDR OUTPUT

Every single candidate design produced the 7 required standard artifacts:
- `design.json` (canonical `DesignDocument`)
- `planner_output.json` (`DesignPlanV2` contract)
- `corel_operations.json` (executable CorelDRAW transaction operations)
- `preview.png` (800px preview image for blind review)
- `output.cdr` (editable CorelDRAW CDR file)
- `metrics.json` (candidate metadata and validation facts)
- `provenance.json` (license class, commercial permissions, sample flags)

# CANDIDATE DIVERSITY

- **Qwen3-1.7B**: 4 distinct layout families ($\ge 3$ required)
- **Antigravity**: 4 distinct layout families ($\ge 3$ required)

# REVIEW QUEUE

- Dedicated review queue alias: `planner_shootout_antigravity_vs_qwen_v1`
- Dedicated queue file: `training/artifacts/benchmarks/20260812_antigravity_vs_qwen_planner/blind_review/review_queue.jsonl`
- Total blind review pair items: 20 items (4 pairs per category)

To launch the review server:
```powershell
python -m training.tools.human_review_server --queue planner_shootout_antigravity_vs_qwen_v1 --port 8004
```

# BLINDING

1. **Anonymous Candidate IDs**: Candidates are assigned IDs `DESIGN_001` through `DESIGN_040`.
2. **Deterministic Randomization**: Left/right candidate placement (`candidate_1` vs `candidate_2`) was randomized deterministically using seed `42`.
3. **Hidden Mapping File**: Planner identities are stored strictly in `training/artifacts/benchmarks/20260812_antigravity_vs_qwen_planner/blind_review/blind_mapping.json`.
4. **Review UI Compliance**: The review server (`http://127.0.0.1:8004/review`) hides model names, planner identity, score heuristics, and generation order.

# CONTACT SHEETS

- **Anonymous Contact Sheet**: `training/artifacts/benchmarks/20260812_antigravity_vs_qwen_planner/blind_review/planner_candidates_hidden_contact_sheet.png` (Shows anonymous design IDs only)
- **Unblinded Audit Contact Sheet**: `training/artifacts/benchmarks/20260812_antigravity_vs_qwen_planner/blind_review/planner_candidates_unblinded_audit.png` (Shows planner identity, for audit only)

# HUMAN REVIEW

```text
status:
WAITING_FOR_BLIND_HUMAN_REVIEW
```

No aesthetic winner is claimed or assumed before the blind human review is performed.
