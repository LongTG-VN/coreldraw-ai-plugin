# Master Implementation Plan - CorelDRAW AI Plugin Agent

Mục tiêu là xây dựng local automation bridge cho phép AI Agent thiết kế bảng hiệu, banner, poster và thiệp trực tiếp trong CorelDRAW bằng lệnh JSON.

## MVP 1.2.0 — hoàn tất

- [x] Kết nối `CorelDRAW.Application` qua pywin32.
- [x] Tự dùng active document hoặc tạo document mới.
- [x] Tạo màu CMYK `0-100`.
- [x] Tạo rectangle, ellipse và artistic text.
- [x] Đặt tên shape để AI tham chiếu ở lệnh tiếp theo.
- [x] Chỉnh outline CMYK.
- [x] Group shape theo tên.
- [x] Xuất PDF bằng `PublishToPDF`.
- [x] Xuất PNG preview bằng `ExportEx`.
- [x] FastAPI validation và error response thống nhất.
- [x] Tài liệu payload trong `COREL_AI_COMMANDS.md`.
- [x] Unit/API test bằng COM mock.
- [x] GitHub Actions chạy test trên Python 3.10-3.12.

## Kiến trúc hiện tại

```text
AI Agent
  -> FastAPI / Pydantic
  -> CorelDrawBridge + ExtendedCorelDrawBridge
  -> Win32 COM Automation
  -> CorelDRAW 2020-2023
```

## Phase tiếp theo

Các mục dưới đây chưa thuộc MVP hiện tại:

- Batch command/transaction để tạo cả layout trong một request.
- Layer management: tạo, đổi tên, khóa, ẩn và sắp xếp layer.
- Import bitmap/logo và PowerClip.
- Polygon, curve, Bezier và boolean operations.
- Align/distribute, rotate, resize và z-order.
- Paragraph text, text fitting và font fallback.
- Save `.cdr`, template và versioning thiết kế.
- Authentication nếu API cần mở ra ngoài localhost.
- Smoke test tự động trên Windows có CorelDRAW thật.
