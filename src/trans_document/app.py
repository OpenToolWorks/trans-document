"""Vietnamese local WebUI: configure, translate, cancel, download."""

import atexit
import multiprocessing
import os
from pathlib import Path

os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")

import gradio as gr

from .jobs import JobRunner, TranslationRequest

OUTPUT_ROOT = Path(__file__).resolve().parents[2] / "outputs"
RUNNER = JobRunner(OUTPUT_ROOT)
atexit.register(RUNNER.shutdown)

LANGUAGES = [("Tiếng Anh", "en"), ("Tiếng Việt", "vi"), ("Tiếng Trung", "zh-CN"),
             ("Tiếng Nhật", "ja"), ("Tiếng Hàn", "ko"), ("Tiếng Pháp", "fr")]
STAGES = {
    "Parse PDF and Create Intermediate Representation": "Phân tích PDF",
    "DetectScannedFile": "Kiểm tra PDF scan",
    "Parse Page Layout": "Nhận diện bố cục trang",
    "Parse Paragraphs": "Nhận diện đoạn văn",
    "Parse Formulas and Styles": "Phân tích công thức và kiểu chữ",
    "Translate Paragraphs": "Dịch đoạn văn",
    "Typesetting": "Dàn trang bản dịch",
    "Add Fonts": "Chuẩn bị font",
    "Generate drawing instructions": "Tạo nội dung PDF",
    "Subset font": "Tối ưu font",
    "Save PDF": "Lưu PDF",
}
ERRORS = {
    "authentication": "API key không hợp lệ hoặc không có quyền dùng model.",
    "quota": "API đang giới hạn tốc độ hoặc hết hạn mức. Kiểm tra quota của dịch vụ.",
    "connection": "Không kết nối được API. Kiểm tra mạng và Base URL.",
    "pdf": "BabelDOC không đọc được PDF này hoặc cần xử lý OCR.",
    "output": "Backend chưa tạo đủ hai PDF hợp lệ; không cung cấp file chưa hoàn tất.",
    "worker": "Tiến trình dịch đã dừng bất thường. Có thể thiếu bộ nhớ hoặc dependency.",
    "backend": "BabelDOC/API gặp lỗi. Kiểm tra tên model, endpoint và khả năng đọc PDF.",
}


def translate_ui(pdf, base_url, model, api_key, lang_in, lang_out, request: gr.Request,
                 runner=RUNNER, progress=gr.Progress()):
    yield "Đang kiểm tra PDF và cấu hình…", None, None, gr.update(interactive=False), gr.update(interactive=True)
    status, mono, dual = "Đã dừng tác vụ.", None, None
    try:
        if not pdf:
            raise ValueError("Vui lòng chọn một file PDF.")
        settings = TranslationRequest(str(pdf), base_url.strip(), model.strip(), api_key,
                                      lang_in, lang_out)
        for event in runner.stream(settings, request.session_hash):
            event_type = event["type"]
            if event_type == "progress":
                stage = STAGES.get(event.get("stage"), event.get("stage", "Đang xử lý"))
                percent = max(0, min(100, float(event.get("percent") or 0)))
                progress(percent / 100, desc=stage)
                yield f"{stage} — {percent:.0f}%", None, None, gr.skip(), gr.skip()
            elif event_type == "finish":
                progress(1, desc="Hoàn tất")
                status = "Hoàn tất. Tải bản dịch hoặc PDF song ngữ bên dưới."
                mono, dual = event["mono"], event["dual"]
            elif event_type == "cancelled":
                status = "Đã hủy tác vụ. Bạn có thể bắt đầu lại."
            elif event_type == "error":
                status = ERRORS.get(event.get("code"), ERRORS["backend"])
    except ValueError as error:
        status = str(error)
    except Exception:
        status = ERRORS["worker"]
    yield status, mono, dual, gr.update(interactive=True), gr.update(interactive=False)


def cancel_ui(request: gr.Request):
    if RUNNER.cancel(request.session_hash):
        return "Đang hủy tiến trình dịch…"
    return "Không có tác vụ đang chạy trong phiên của bạn."


def disconnect(request: gr.Request):
    RUNNER.cancel(request.session_hash)


def build_app():
    with gr.Blocks(title="TransDocument", theme=gr.themes.Soft(), analytics_enabled=False,
                   delete_cache=(3600, 86400)) as app:
        gr.Markdown("# TransDocument\nDịch PDF với **BabelDOC** · Giữ bố cục và công thức · Chạy trên máy của bạn")
        with gr.Row():
            with gr.Column(scale=1):
                pdf = gr.File(label="Tài liệu PDF", file_types=[".pdf"], type="filepath", file_count="single")
                with gr.Row():
                    lang_in = gr.Dropdown(LANGUAGES, value="en", label="Ngôn ngữ nguồn")
                    lang_out = gr.Dropdown(LANGUAGES, value="vi", label="Ngôn ngữ đích")
                base_url = gr.Textbox(label="Base URL — OpenAI-compatible",
                                      value="https://generativelanguage.googleapis.com/v1beta/openai/")
                model = gr.Textbox(label="Model", value="gemini-3.1-flash-lite")
                api_key = gr.Textbox(label="API key", type="password", value="",
                                     placeholder="Nhập key của dịch vụ bạn chọn")
                gr.Markdown("Key chỉ giữ trong bộ nhớ phiên chạy, không lưu vào cấu hình. "
                            "Text tài liệu được gửi đến dịch vụ API bạn chọn để dịch.")
                with gr.Row():
                    start = gr.Button("Dịch PDF", variant="primary")
                    cancel = gr.Button("Hủy", interactive=False)
            with gr.Column(scale=1):
                status = gr.Textbox(label="Trạng thái", value="Sẵn sàng. Chọn PDF và nhập API key.",
                                    interactive=False, lines=3)
                mono = gr.File(label="PDF bản dịch", interactive=False)
                dual = gr.File(label="PDF song ngữ", interactive=False)
                gr.Markdown("**Lần chạy đầu:** BabelDOC có thể tải model layout và font. "
                            "Kết quả được giữ trong thư mục `outputs/`. "
                            "Mỗi lần chỉ chạy một tác vụ; nút Hủy dừng tiến trình dịch.")
        start.click(translate_ui, inputs=[pdf, base_url, model, api_key, lang_in, lang_out],
                    outputs=[status, mono, dual, start, cancel], concurrency_limit=None,
                    api_name=False)
        cancel.click(cancel_ui, outputs=status, queue=False, api_name=False)
        app.unload(disconnect)
    return app.queue(default_concurrency_limit=1, max_size=8)


def main():
    multiprocessing.freeze_support()
    app = build_app()
    app.launch(server_name="127.0.0.1", server_port=7860, share=False,
               inbrowser=True, show_error=False, show_api=False)


if __name__ == "__main__":
    main()
