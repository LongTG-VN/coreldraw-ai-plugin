# CORELDRAW AI PLUGIN AGENT - INSTRUCTION & ARCHITECTURE

Dự án: **CorelDRAW AI Plugin Agent**
Vị trí thư mục: `d:\codex\coreldraw-ai-plugin`

---

## 🎯 MỤC TIÊU DỰ ÁN

Tạo ra giải pháp giao tiếp (Plugin / API Bridge) kết nối giữa **AI Agent (Vision-Action AI)** và phần mềm **CorelDRAW** trên Windows:
- Cho phép AI gửi câu lệnh JSON qua REST API để tự động tạo đối tượng Vector (Hình chữ nhật, hình tròn, đường cong, Text).
- Tự động thay đổi màu sắc Fill (RGB/CMYK), cài đặt Font chữ, kích thước, hiệu ứng căn chỉnh (Alignment) trong CorelDRAW giống như thao tác của một Designer chuyên nghiệp.

---

## 🏗️ CẾT CẤU MÃ NGUỒN (ARCHITECTURE)

```
[Vision-Action AI Agent] 
        │ (Gửi câu lệnh thiết kế JSON qua HTTP)
        ▼
[FastAPI Server: main.py (Port 8001)] 
        │ (Truyền lệnh xuống Win32 COM Interface)
        ▼
[CorelDRAW Automation Bridge: corel_bridge.py] 
        │ (Điều khiển trực tiếp tiến trình CorelDRAW.exe)
        ▼
[CorelDRAW Application Canvas] (Tự động vẽ Vector / Chèn Text)
```

---

## 📁 CÁC FILE CHÍNH

1. [`corel_bridge.py`](file:///d:/codex/coreldraw-ai-plugin/corel_bridge.py): Module tương tác Win32 COM Automation trực tiếp với `CorelDRAW.Application`.
2. [`main.py`](file:///d:/codex/coreldraw-ai-plugin/main.py): REST API Server (FastAPI) nhận yêu cầu thiết kế từ AI Agent.
3. [`requirements.txt`](file:///d:/codex/coreldraw-ai-plugin/requirements.txt): Cài đặt `pywin32`, `fastapi`, `uvicorn`.

---

## 🚀 HƯỚNG DẪN KHỞI CHẠY LẦN ĐẦU

```bash
# 1. Cài đặt các gói phụ thuộc
pip install -r requirements.txt

# 2. Khởi chạy CorelDRAW trên máy Windows
# 3. Chạy REST API Bridge cho AI Agent
python main.py
```
Sau đó AI Agent chỉ cần gửi HTTP POST tới `http://127.0.0.1:8001/api/v1/corel/rectangle` hoặc `/text` để CorelDRAW tự động thiết kế!
