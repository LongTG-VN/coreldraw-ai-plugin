# CODEX MASTER INSTRUCTION - CORELDRAW AUTOMATION FRAMEWORK

Dự án: **CorelDRAW AI Plugin Agent**
Vị trí thư mục: `d:\codex\coreldraw-ai-plugin`

---

## 💡 NGUYÊN LÝ KẾT NỐI OPEN-SOURCE DÀNH CHO CODEX

Cộng đồng Open-Source tự động hóa CorelDRAW sử dụng chung giao thức chuẩn **Win32 COM Automation Server** (via `pywin32` package).
Mọi câu lệnh VBA Macro nguyên bản trong CorelDRAW đều tương thích 100% với Python:

- **VBA Syntax**: `CorelDRAW.Application.ActiveDocument.ActivePage.CreateRectangle(...)`
- **Python Syntax**: `win32com.client.Dispatch("CorelDRAW.Application").ActiveDocument.ActivePage.CreateRectangle(...)`

---

## 📋 DANH SÁCH MÃ NGUỒN VÀ MỤC ĐÍCH

1. [`corel_bridge.py`](file:///d:/codex/coreldraw-ai-plugin/corel_bridge.py):
   - Chứa kết nối COM lõi `win32com.client`.
   - Chứa các hàm tạo Shape cơ bản: `create_rectangle_cmyk()`, `create_ellipse_cmyk()`, `create_artistic_text_cmyk()`.
   - Chứa khởi tạo hệ màu CMYK chuẩn in ấn quảng cáo: `CreateCMYKColor(c, m, y, k)`.

2. [`extended_bridge.py`](file:///d:/codex/coreldraw-ai-plugin/extended_bridge.py):
   - Chứa các tính năng tự động hóa nâng cao:
     - `set_shape_outline_cmyk()`: Cài đặt đường viền Outline.
     - `group_shapes_by_names()`: Gom nhóm layer thiết kế.
     - `export_to_pdf()`: Xuất file PDF chuẩn in ấn.

3. [`main.py`](file:///d:/codex/coreldraw-ai-plugin/main.py):
   - Cung cấp giao diện REST API Server (FastAPI) tại `http://127.0.0.1:8001` nhận lệnh JSON từ AI Agent để tự động vẽ trong CorelDRAW.

4. [`CODEX_SPECIFICATION.md`](file:///d:/codex/coreldraw-ai-plugin/CODEX_SPECIFICATION.md):
   - File hướng dẫn nhiệm vụ mở rộng cho Codex AI.

---

## 🛠️ HƯỚNG DẪN CODEX LẬP TRÌNH THÊM TÍNH NĂNG MỚI

Khi bạn (Codex AI) muốn bổ sung tính năng tự động vẽ mới (Ví dụ: Vẽ Polygon, Thêm Hiệu ứng Drop Shadow, Nhập file ảnh Bitmap vào Canvas):
1. Tra cứu cú pháp VBA tương ứng của CorelDRAW.
2. Viết phương thức tương ứng vào [`extended_bridge.py`](file:///d:/codex/coreldraw-ai-plugin/extended_bridge.py).
3. Đăng ký Endpoint HTTP mới trong [`main.py`](file:///d:/codex/coreldraw-ai-plugin/main.py).
