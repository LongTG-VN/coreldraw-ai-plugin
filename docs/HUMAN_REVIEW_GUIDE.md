# Hướng dẫn chấm thiết kế — Design AI v0.4 Phase 1

Bạn không cần sửa JSON và không cần chạy model khi chấm. Candidate đã được tạo và kiểm tra kỹ thuật trước khi vào hàng đợi.

## Pilot Phase 1.2 — ưu tiên chấm trước

Phase 1.2 chỉ chứa ba category yếu nhất theo review thật: SALE, SIGNAGE và SPA.
Mở đúng queue tách biệt bằng lệnh:

```powershell
cd D:\codex\coreldraw-ai-plugin
python -m training.tools.human_review_server --queue v04_phase1_2_category_pilot --port 8004
```

Mở `http://127.0.0.1:8004/review`. Queue có 12 so sánh mù; version,
quality-floor metrics và nhãn cũ/mới đều bị ẩn trong lúc chấm. Nên nhập điểm
`Chất lượng tổng thể` 1–10 để kiểm tra gate Phase 1.2, nhưng trường này không bắt
buộc.

## Pilot Phase 1.1 — đã hoàn tất vòng chẩn đoán

Việc chấm pool cũ đang tạm dừng vì phản hồi chẩn đoán chỉ khoảng 4/10. Mở riêng pilot đã harden bằng lệnh:

```powershell
cd D:\codex\coreldraw-ai-plugin
python -m training.tools.human_review_server --queue v04_phase1_1_pilot --port 8003
```

Mở `http://127.0.0.1:8003/review`. Pilot có 20 so sánh mù thuộc SPA, CAFE, SALE, MENU và SIGNAGE. Ô chất lượng tổng thể 1–10 được đặt nổi bật nhưng vẫn không bắt buộc.

## 1. Mở trang review

Từ thư mục repository, chạy:

```powershell
python -m training.tools.human_review_server
```

Sau đó mở:

```text
http://127.0.0.1:8002/review
```

Server chỉ lắng nghe trên máy local (`127.0.0.1`).

## 2. Chấm thiết kế

1. Nhập tên reviewer, ví dụ `Long` hoặc `Designer_01`.
2. Đọc brief và category.
3. So sánh hai hình cùng tỷ lệ, có thể bấm hình để phóng to.
4. Chọn nhanh bằng nút hoặc bàn phím:
   - `A`: Design A đẹp hơn.
   - `D` hoặc `B`: Design B đẹp hơn.
   - `T`: hòa.
   - `X`: cả hai đều xấu.
   - `S`: bỏ qua.
5. Điểm composition, hierarchy, typography, brand feeling, overall và ghi chú đều không bắt buộc.

Sau mỗi lựa chọn, hệ thống lưu ngay rồi chuyển sang pair kế tiếp. Đóng browser hoặc restart server không làm mất review đã lưu. Nhập lại cùng tên reviewer để tiếp tục phiên chưa hoàn tất.

Trang đang chấm cố ý không hiển thị version, model, seed, iteration, heuristic score hay critic score. A/B đã được random cố định cho từng session để hạn chế bias.

## 3. Xem tiến độ

Mở:

```text
http://127.0.0.1:8002/review/summary
```

Summary chỉ tổng hợp hành động thực của reviewer. Nó không tạo winner tự động.

## 4. Export preference dataset

Sau khi có review thật, chạy:

```powershell
python -m training.tools.export_preferences `
  --queue training/artifacts/preference/v0_4_initial_pool/review_queue/review_queue.jsonl `
  --artifact-root training/artifacts `
  --output training/data/human_preferences/v0_4/exports/latest
```

Output:

- `preference_pairs.jsonl`: chỉ chứa lựa chọn A/B có human verification.
- `preference_summary.json`: thống kê A/B/tie/both-bad/category/reviewer và training gate.
- `review_validation_report.json`: lỗi file, identity, duplicate, provenance và license.
- `brief_split.json`: split theo `brief_id`, không làm rò pair cùng brief qua train/test.

Tie và both-bad vẫn được giữ trong review gốc nhưng không bị ép thành chosen/rejected.

## Quy tắc quan trọng

- Không sửa file review bằng tay.
- Không coi heuristic, VLM, critic hay metric là human preference.
- Chỉ train reranker khi exporter báo tối thiểu 80 non-tie pair, 20 brief và 8 category.
- Candidate và preference hiện vẫn research-only vì checkpoint/reference corpus chứa GenPoster CC-BY-NC.
