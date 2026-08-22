# Corel Agent Vietnamese Commands

## Purpose

The current analyzer is a conservative deterministic gate, not a natural-language model. It normalizes common Vietnamese forms and decides whether a request is explicit enough to enter structured planning.

## Supported explicit forms

- `đổi số điện thoại thành ...`
- `thay sđt thành ...`
- `sửa phone thành ...`
- `đổi giá 250k thành 299k`
- `dịch logo qua phải 2mm`
- `logo lớn thêm 10%`

The deterministic planner also supports established explicit object-ID forms for move, resize, rotate, font family, and font size.

## Constraints

- `giữ nguyên mọi thứ khác` -> `PRESERVE_ALL_UNTARGETED_OBJECTS`
- `đừng sửa logo` / `không sửa logo` -> `PRESERVE_LOGO`
- `file nào không chắc thì bỏ qua` -> `SKIP_ON_UNCERTAINTY`

A constraint alone is not an executable action and requires review.

## Fail-closed requests

The following are `PLAN_REVIEW_REQUIRED`:

- missing business values, such as `đổi tên và số điện thoại`;
- vague aesthetic intent, such as `làm cho đẹp`;
- broad mutation, such as `sửa hết`;
- vague deletion, such as `xoá mấy cái dư`;
- unconstrained discretion, such as `chỉnh đại` or `tự quyết định`.

Output-only commands (`xuất PDF`, `xuất PNG`, `xuất CDR`, `lưu thành bản mới`, `undo`) are classified `OUTPUT_ONLY_UNSUPPORTED` at the mutation-planner boundary. This prevents output intent from being mistaken for mutation authority.

## Benchmark

Run:

```powershell
python -m training.tools.benchmark_corel_agent_planner --output training/workspace/operator_overnight/vietnamese_benchmark.json
```

Current hermetic evidence: 24/24 cases passed and 6/6 unsafe or vague cases were refused. The result records `planner_type=deterministic` and `planner_is_ai=false`.

## Limitations

This is not open-ended language understanding. Unsupported wording, multiple ambiguous targets, missing values, and aesthetic requests require review. Future model comparisons must use the same schema and provenance fields and remain plan-only until separately authorized.
