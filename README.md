# TransDocument

WebUI tiếng Việt chạy local, dùng **BabelDOC 0.6.4** để phân tích PDF, bảo toàn công thức và dàn trang. Dịch text bằng Gemini, OpenAI hoặc dịch vụ OpenAI-compatible. Tạo PDF bản dịch và PDF song ngữ.

## Chạy trên Windows

Yêu cầu Python 3.12 (64-bit). Tại thư mục project:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m trans_document
```

Môi trường `.venv` đã được tạo nếu bạn đang sử dụng checkout này sau bước cài đặt. Khi đó chỉ cần lệnh cuối.

Mở **http://127.0.0.1:7860** nếu trình duyệt chưa tự mở. Dừng ứng dụng bằng `Ctrl+C` trong terminal.

## Cài đặt API

Mở tab **Cài đặt API** để thêm, sửa, kiểm tra, đặt mặc định hoặc xóa kết nối. Có preset cho Gemini và OpenAI. Cấu hình dịch vụ được lưu tại `%LOCALAPPDATA%\TransDocument\profiles.json` trên Windows. File chỉ chứa tên, nhà cung cấp, Base URL, model và ID kết nối, không có API key.

Nhập key rồi bấm **Lưu kết nối**. Key chỉ giữ trong phiên trình duyệt hiện tại. Tải lại trang, đóng tab hoặc khởi động lại ứng dụng thì cần nhập lại key. Mỗi tab có key riêng. Bấm **Kiểm tra kết nối** để gửi yêu cầu ngắn `Hello`; yêu cầu này có thể tính vào quota của dịch vụ.

## Dịch một PDF

1. Chọn PDF, ngôn ngữ nguồn/đích (mặc định Anh → Việt) và kết nối API.
2. Chọn **Toàn bộ tài liệu** hoặc dịch thử 1–3 trang đầu để xem thử kết quả.
3. Bấm **Dịch PDF**, theo dõi tiến trình từng giai đoạn. Có thể bấm **Hủy** khi tác vụ đang chạy.
4. Xem ảnh trang đầu của bản gốc và bản dịch, rồi tải **PDF bản dịch** hoặc **PDF song ngữ**.

Gemini (kết nối mặc định ban đầu):

```text
Base URL: https://generativelanguage.googleapis.com/v1beta/openai/
Model:    gemini-3.1-flash-lite
```

Bạn có thể thay bằng endpoint/model OpenAI-compatible khác. Khả năng dùng model phụ thuộc dịch vụ và quyền của API key.
Ứng dụng gửi yêu cầu dịch ngắn `Hello` trước khi xử lý PDF để kiểm tra API; yêu cầu này cũng tính vào quota của dịch vụ.

## File, model và cache

- PDF được xử lý local; **text tài liệu được gửi đến API bạn cấu hình**.
- Lần đầu BabelDOC có thể tải model layout/font; cần mạng và có thể mất vài phút. UI vẫn có thể hủy khi khởi tạo.
- Mỗi tác vụ có thư mục `outputs/<job-id>/` riêng. Tác vụ lỗi/hủy không cung cấp PDF dở dang.
- Job thành công giữ bản input và kết quả trong `outputs/`. Xóa thư mục job khi không cần nữa.
- BabelDOC quản lý cache model/font và bản dịch riêng, thường dưới thư mục cache của người dùng. Translation cache có thể chứa text nguồn/đích; không chứa API key do ứng dụng truyền vào.
- Một tác vụ chạy tại một thời điểm. API key chỉ nằm trong bộ nhớ phiên trình duyệt/server/worker; tải lại trang sẽ yêu cầu nhập lại key.
- Worker không in raw lỗi provider hoặc text ra application log; UI hiển thị nhóm lỗi (key/quota/kết nối/PDF/backend).

## Kiểm tra

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Tests dùng một worker giả để kiểm tra vòng đời tác vụ, đầu ra PDF, hủy và UI, không gọi API trả phí. Chất lượng dịch cần kiểm tra với PDF/model thực tế của bạn.

Kiểm tra tích hợp BabelDOC thật với endpoint giả lập local (không gọi Gemini, có thể tải model/font):

```powershell
.\.venv\Scripts\python.exe -m scripts.smoke_backend
```

## Cấu trúc

```text
src/trans_document/
  app.py          Gradio UI, cài đặt API và hiển thị tiến trình
  jobs.py         Validation, thư mục job, multiprocessing và hủy
  profiles.py     Metadata kết nối API lưu trên máy, không lưu key
  preview.py      Ảnh xem trước PDF giới hạn độ phân giải
  ui.css          Bố cục responsive cho giao diện
  worker.py       Kiểm tra API và BabelDOC translator/config
  __main__.py     Entry point: python -m trans_document
tests/            Kiểm tra tự động không gọi API trả phí
scripts/
  smoke_backend.py  Kiểm tra tích hợp BabelDOC thật với API local
docs/             Tài liệu thiết kế/kế hoạch local, được Git ignore
outputs/          PDF nguồn và kết quả, được Git ignore
pyproject.toml    Dependencies và cấu hình package
```

## Giấy phép

Copyright (C) 2026 TransDocument contributors.

TransDocument được phân phối theo **GNU Affero General Public License, chỉ phiên bản 3 (AGPL-3.0-only)**. Bạn có thể sử dụng, sửa đổi và phân phối theo các điều khoản của giấy phép. Phần mềm được cung cấp không có bảo hành, kể cả bảo hành về khả năng thương mại hoặc phù hợp với một mục đích cụ thể.

Toàn văn giấy phép nằm trong [`LICENSE`](LICENSE). Thông tin về các thư viện, model và font bên thứ ba nằm trong [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md); các thành phần này giữ nguyên giấy phép riêng của chúng.
