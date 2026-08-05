# CorelDRAW AI Plugin Agent

REST API chạy cục bộ trên Windows, cho phép AI Agent điều khiển CorelDRAW qua Win32 COM Automation để tạo vector CMYK, chỉnh outline, group đối tượng và xuất file.

## Trạng thái MVP

Đã hỗ trợ:

- Kết nối CorelDRAW 2020-2023 và tự tạo document nếu chưa có file mở.
- Tạo rectangle, ellipse và artistic text với màu CMYK.
- Đặt tên shape ổn định để AI dùng lại ở các lệnh sau.
- Chỉnh outline CMYK và group nhiều shape.
- Xuất PDF in ấn và PNG preview.
- Validate request bằng Pydantic, trả lỗi JSON rõ ràng.
- Test bằng COM mock nên có thể chạy CI trên Linux mà không cần cài CorelDRAW.

## Kiến trúc

```text
AI Agent
   │ JSON / HTTP
   ▼
FastAPI (main.py, 127.0.0.1:8001)
   │
   ├── CorelDrawBridge: shape/text/CMYK
   └── ExtendedCorelDrawBridge: outline/group/export
   │ Win32 COM Automation
   ▼
CorelDRAW trên Windows
```

Mỗi lệnh mở một COM session ngắn và được khóa tuần tự để tránh xung đột thread giữa FastAPI và CorelDRAW.

## Yêu cầu

- Windows 10/11 64-bit.
- CorelDRAW 2020, 2021, 2022 hoặc 2023.
- Python 3.10 trở lên.

## Cài đặt

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Mở CorelDRAW trước, sau đó chạy API:

```powershell
python main.py
```

- API: `http://127.0.0.1:8001`
- Swagger UI: `http://127.0.0.1:8001/docs`
- Health check: `http://127.0.0.1:8001/health`

Server mặc định chỉ bind vào `127.0.0.1`. Không đổi sang `0.0.0.0` nếu chưa bổ sung authentication và firewall.

## Endpoint chính

| Method | Endpoint | Chức năng |
|---|---|---|
| `GET` | `/health` | Kiểm tra HTTP service, không mở CorelDRAW |
| `POST` | `/api/v1/corel/connect` | Kiểm tra COM và active document |
| `POST` | `/api/v1/corel/shape/rectangle` | Tạo rectangle CMYK |
| `POST` | `/api/v1/corel/shape/ellipse` | Tạo ellipse CMYK |
| `POST` | `/api/v1/corel/text/artistic` | Tạo artistic text CMYK |
| `POST` | `/api/v1/corel/shape/outline` | Chỉnh outline theo tên shape |
| `POST` | `/api/v1/corel/shape/group` | Group nhiều shape |
| `POST` | `/api/v1/corel/export` | Xuất PDF hoặc PNG |

Danh sách payload đầy đủ nằm trong [COREL_AI_COMMANDS.md](COREL_AI_COMMANDS.md).

## Quy ước tọa độ

- `x`, `y` là góc trái trên.
- `width`, `height` phải lớn hơn `0`.
- Đơn vị phụ thuộc vào unit hiện tại của document CorelDRAW.
- API tính bounding box theo `left=x`, `top=y`, `right=x+width`, `bottom=y-height`.

## Export

- `pdf`: dùng `Document.PublishToPDF`, phù hợp file in.
- `png`: dùng `Document.ExportEx` ở RGB, phù hợp preview; DPI từ 72 đến 1200.
- Nếu thiếu extension, server tự thêm `.pdf` hoặc `.png`.
- Thư mục cha được tạo tự động.

## Chạy test

```bash
pip install -r requirements-dev.txt
pytest -q
```

Test không gọi CorelDRAW thật. Khi triển khai trên Windows vẫn cần kiểm tra smoke test với đúng phiên bản CorelDRAW và profile màu của máy in.
