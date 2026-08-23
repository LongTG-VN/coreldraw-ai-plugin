# Corel AI Operator V1

## Trạng thái

Đây là ứng dụng local-first để inspect CDR, lập plan bằng Codex qua Corel MCP,
xin xác nhận của người dùng và chỉ thực thi trên working copy. File nguồn luôn
read-only. V1 hiện dùng được cho thay text có target rõ ràng, multi-action text
và export; MOVE/RESIZE vẫn bị policy hiện hành giữ lại để review nên checkpoint
này được phân loại `COREL_AI_OPERATOR_V1_PARTIAL`.

## Khởi động

Yêu cầu: Windows, Python của dự án, CorelDRAW, Codex CLI đã đăng nhập, MCP
`corel_operator` đã đăng ký, và inventory local tại
`training/workspace/company_archive/archive.sqlite`.

Từ thư mục repository, chạy một trong hai cách:

```powershell
.\start_corel_ai.bat
```

hoặc:

```powershell
python -m training.tools.corel_codex_ui --ensure-corel --open-browser --port 8004
```

Launcher kiểm tra Python, inventory, CorelDRAW, MCP, Operator workspace, đăng
nhập Codex và port 8004. Khi sẵn sàng, terminal in `READY` và mở:

```text
http://127.0.0.1:8004/corel-ui
```

Nếu V1 đã chạy trên port này, chạy launcher lần nữa chỉ mở lại UI hiện hữu;
không tạo service hoặc Corel worker thứ hai.

Có thể kiểm tra prerequisite mà không mở server:

```powershell
python -m training.tools.corel_codex_ui --preflight-only
```

Không sửa registry hay global config trong quá trình startup.

## Quy trình sử dụng

1. Nhập opaque inventory ID dạng `file:...`, rồi chọn **Inspect document**.
2. Nhập lệnh tiếng Việt hoặc chọn preset.
3. Chọn **Ask Codex to plan** và đọc plan, target, giá trị, risk.
4. Chỉ khi **Approve** bật, xác nhận để tạo working copy và chạy transaction.
5. Kiểm tra Visual QA, Before / After / Diff và thông báo recovery.
6. Mở hoặc tải CDR/PDF/PNG từ khu vực Outputs.

Luồng thực thi là:

```text
source read-only -> plan -> policy -> explicit approval -> working copy
-> transaction -> structural/visual QA -> save -> reopen -> versioned outputs
```

Một failure trong transaction phải rollback/fail closed. UI không hiển thị raw
stack trace ở chế độ thường; chi tiết chẩn đoán nằm trong **Debug details**.

## Preset và lệnh thường dùng

Các preset chỉ điền lệnh vào ô command; chúng vẫn qua Codex/MCP, schema, policy
và approval như lệnh nhập tay.

```text
Đổi nội dung object static_31 thành TÊN MỚI
Đổi số điện thoại 0292 123 456 thành 0909 111 222
Đổi địa chỉ cũ thành ĐỊA CHỈ MỚI
Đổi giá 50K thành 55K
Di chuyển object static_36 sang phải 1mm
Tăng kích thước object static_36 lên 5%
Xuất file PDF và PNG
```

Không dùng yêu cầu mơ hồ như “đổi tất cả cho đẹp hơn”. Không phát minh tên,
giá, số điện thoại, địa chỉ hay nội dung kinh doanh không được cung cấp.

## Health

Header hiển thị bốn trạng thái độc lập:

- `COREL`: tiến trình CorelDRAW có sẵn.
- `MCP`: MCP `corel_operator` được bật.
- `OPERATOR`: inventory tồn tại và workspace ghi được.
- `CODEX`: Codex CLI tồn tại và đã đăng nhập.

API health local:

```powershell
Invoke-RestMethod http://127.0.0.1:8004/api/v1/corel-ui/status
```

Nếu một thành phần không READY, startup fail closed và in hành động cần làm.

## Recent jobs và outputs

Job history được lưu local trong workspace SQLite, nên reload trình duyệt không
làm mất các job đã hoàn tất. Không có dữ liệu nào được gửi lên cloud ngoài lời
gọi Codex planner đã được người dùng yêu cầu; source path không được đưa vào
plan và Corel MCP chỉ nhận opaque file ID.

Output mặc định:

```text
training/workspace/company_archive/operator_codex_ui/jobs/<job-id>/v001/
  output.cdr
  output.pdf
  output.png
  before.png
  after.png
  diff.png
```

Nếu cùng task được publish lại an toàn, version tiếp theo là `v002`, `v003`, …;
source không bao giờ bị overwrite. UI có **Open folder**, **Open CDR**,
**Open PDF**, **Open PNG**. Các đường dẫn chỉ được resolve bên trong workspace.

Settings local gồm output subfolder, PDF/PNG mặc định, preview quality và số job
gần đây. `standard` giảm kích thước ảnh QA tối đa 1600 px; `high` giữ ảnh QA
gốc. CDR luôn bắt buộc và không bị rasterize.

## Recovery và shutdown

- `NEEDS_REVIEW`: không mutation; làm rõ target/value hoặc dùng object ID.
- Corel/MCP offline: sửa health trước rồi lập plan lại.
- Save/reopen/QA failure: job fail closed; đọc recovery message và debug details.
- Source safety failure: dừng, không dùng output.
- **Restart service** chỉ hoạt động khi không có job đang chạy.
- **Safe shutdown** từ UI hoặc `Ctrl+C` trong terminal chỉ dừng service khi idle.

Đóng tab trình duyệt không tự dừng server. Khi một job đang thực thi, lifecycle
request bị từ chối để transaction hoàn tất hoặc rollback an toàn.

## Real-use smoke của checkpoint

Một CDR công ty được truy cập qua opaque ID; source không bị sửa.

| Job | Kết quả | Save/reopen | QA |
| --- | --- | --- | --- |
| TEXT_REPLACE | AUTO_SUCCESS | PASS | PASS |
| MOVE | NEEDS_REVIEW (medium-risk policy) | không chạy | WAITING |
| RESIZE | NEEDS_REVIEW (medium-risk policy) | không chạy | WAITING |
| MULTI_ACTION (2 text actions/1 transaction) | AUTO_SUCCESS | PASS | PASS |
| EXPORT_ONLY (CDR/PDF/PNG) | AUTO_SUCCESS | PASS | PASS |

Tổng: 5 job, 3 success, 2 correctly held for review, 0 failed, 0 source
mutation. Các artifact thực tế nằm trong local ignored workspace, không commit.

## Giới hạn đã biết

- Đây là local Windows/Corel workflow, không phải cloud deployment.
- MOVE/RESIZE do Codex lập đúng plan nhưng vẫn bị policy agent hiện hành giữ ở
  `NEEDS_REVIEW`; V1 không nới quyền mutation trong milestone này.
- Recent job history lưu instruction và opaque ID local; người vận hành phải tự
  quản lý quyền truy cập máy/workspace.
- Preset không thay thế việc inspect target và kiểm tra plan.
- Không có installer; launcher `.bat` là trải nghiệm đóng gói của V1.
