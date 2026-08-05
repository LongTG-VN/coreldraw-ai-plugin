# CorelDRAW AI Commands

Base URL mặc định: `http://127.0.0.1:8001`

Tất cả màu CMYK dùng thang `0-100`:

```json
{
  "cyan": 0,
  "magenta": 100,
  "yellow": 100,
  "black": 0
}
```

## Health check

```http
GET /health
```

## Connect CorelDRAW

```http
POST /api/v1/corel/connect
```

## Create rectangle

```http
POST /api/v1/corel/shape/rectangle
Content-Type: application/json
```

```json
{
  "x": 0,
  "y": 20,
  "width": 30,
  "height": 10,
  "name": "background",
  "color": {
    "cyan": 0,
    "magenta": 100,
    "yellow": 100,
    "black": 0
  }
}
```

## Create ellipse

```http
POST /api/v1/corel/shape/ellipse
Content-Type: application/json
```

```json
{
  "x": 2,
  "y": 18,
  "width": 5,
  "height": 5,
  "name": "logo_circle",
  "color": {
    "cyan": 100,
    "magenta": 0,
    "yellow": 0,
    "black": 0
  }
}
```

## Create artistic text

```http
POST /api/v1/corel/text/artistic
Content-Type: application/json
```

```json
{
  "text": "QUẢNG CÁO KHÁ THUẬN",
  "x": 4,
  "y": 15,
  "font_name": "Arial",
  "font_size": 36,
  "name": "brand_title",
  "color": {
    "cyan": 0,
    "magenta": 0,
    "yellow": 0,
    "black": 100
  }
}
```

## Set outline

```http
POST /api/v1/corel/shape/outline
Content-Type: application/json
```

```json
{
  "shape_name": "logo_circle",
  "width": 0.2,
  "color": {
    "cyan": 0,
    "magenta": 0,
    "yellow": 0,
    "black": 100
  }
}
```

## Group shapes

```http
POST /api/v1/corel/shape/group
Content-Type: application/json
```

```json
{
  "shape_names": ["background", "logo_circle", "brand_title"],
  "group_name": "signboard_header"
}
```

## Export PDF

```http
POST /api/v1/corel/export
Content-Type: application/json
```

```json
{
  "file_path": "D:\\CorelExports\\signboard-final.pdf",
  "format": "pdf",
  "dpi": 300
}
```

## Export PNG preview

```json
{
  "file_path": "D:\\CorelExports\\signboard-preview.png",
  "format": "png",
  "dpi": 150
}
```

Lỗi CorelDRAW/COM trả HTTP `503`; payload sai hoặc CMYK ngoài `0-100` trả `422`.

Workflow đề xuất cho AI Agent: connect → tạo shape/text → chỉnh outline → group → xuất PNG duyệt nhanh → xuất PDF in.
