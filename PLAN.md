# Master Implementation Plan - CorelDRAW AI Plugin Agent

Kế hoạch chi tiết xây dựng hệ thống **CorelDRAW AI Plugin Agent** cho phép AI tự động thiết kế Bảng hiệu, Banner quảng cáo, Poster và Thiệp theo chuẩn in ấn CMYK trực tiếp trên phần mềm CorelDRAW (2020-2023).

---

## 🏗️ Tổng Quan Kiến Trúc (Architecture)

```
[AI Vision-Action Agent / Codex]
               │ (JSON CMYK Commands)
               ▼
[FastAPI Local Server: main.py]
               │ (Pydantic Validation)
               ▼
[CorelDRAW COM Bridge: corel_bridge.py]
               │ (Win32 COM Automation)
               ▼
[CorelDRAW 2020-2023 Application Canvas .CDR]
```

---

## 🎯 Phạm Vi & Yêu Cầu Kỹ Thuật

1. **Phiên bản hỗ trợ**: CorelDRAW 2020 / 2021 / 2022 / 2023 (Windows 64-bit).
2. **Chuẩn màu sắc**: Chuẩn màu **CMYK** dành cho in ấn ngành quảng cáo (`C, M, Y, K` 0-100%).
3. **Các nhóm lệnh AI hỗ trợ**:
   - `create_rectangle_cmyk(x, y, w, h, c, m, y, k)`: Tạo khung bảng hiệu, background.
   - `create_ellipse_cmyk(x, y, r, c, m, y, k)`: Tạo bo tròn, họa tiết trang trí.
   - `create_artistic_text(text, x, y, font_name, font_size, c, m, y, k)`: Tạo tiêu đề, hotline, địa chỉ trên bảng hiệu.
   - `group_shapes(shape_names)`: Nhóm các lớp thiết kế thành Group.
   - `export_to_pdf_or_image(filepath, format)`: Tự động xuất file in PDF/EPS hoặc PNG xem thử.

---

## 📁 Detailed Task Breakdown for Codex

### Task 1: Module `corel_bridge.py` Upgrade
- Hỗ trợ kết nối Win32 COM với `CorelDRAW.Application`.
- Hàm `CreateCMYKColor(c, m, y, k)` khởi tạo màu in ấn chuẩn.
- Các hàm vẽ vector: `create_rectangle`, `create_ellipse`, `create_artistic_text`.

### Task 2: Module `main.py` REST API Server
- Định nghĩa Pydantic Models cho màu CMYK.
- Thêm REST Endpoints:
  - `POST /api/v1/corel/shape/rectangle`
  - `POST /api/v1/corel/shape/ellipse`
  - `POST /api/v1/corel/text/artistic`
  - `POST /api/v1/corel/export`

### Task 3: Command Documentation (`COREL_AI_COMMANDS.md`)
- Tạo tài liệu mẫu danh sách câu lệnh JSON chuẩn để AI Agent tra cứu khi thiết kế.
