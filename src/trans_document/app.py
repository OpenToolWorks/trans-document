"""Vietnamese local PDF translation UI."""

import atexit
import ipaddress
import multiprocessing
import os
import threading
from pathlib import Path
from urllib.parse import urlsplit

os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")

import gradio as gr

from .jobs import JobRunner, TranslationRequest, pdf_page_count
from .preview import render_first_page
from .profiles import (
    ProfileCatalog,
    ProfileStore,
    profile_store_path,
    validate_base_url,
)
from .worker import check_connection

OUTPUT_ROOT = Path(__file__).resolve().parents[2] / "outputs"
RUNNER = JobRunner(OUTPUT_ROOT)
atexit.register(RUNNER.shutdown)
PROFILE_STORE = ProfileStore(profile_store_path())
_PROBE_GENERATIONS = {}
_PROBE_LOCK = threading.Lock()

LANGUAGES = [
    ("Tiếng Anh", "en"), ("Tiếng Việt", "vi"), ("Tiếng Trung", "zh-CN"),
    ("Tiếng Nhật", "ja"), ("Tiếng Hàn", "ko"), ("Tiếng Pháp", "fr"),
]
PROVIDERS = [
    ("Google Gemini", "gemini"), ("OpenAI", "openai"),
    ("OpenAI-compatible", "custom"),
]
PROVIDER_DEFAULTS = {
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai/", "gemini-3.1-flash-lite"),
    "openai": ("https://api.openai.com/v1/", "gpt-4.1-mini"),
    "custom": ("", ""),
}
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


def save_profile(profile_id, name, provider, base_url, model, api_key, keys, store=PROFILE_STORE):
    keys = dict(keys or {})
    try:
        profile_id = profile_id or None
        previous = next((profile for profile in store.read().profiles if profile.id == profile_id), None)
        profile = store.save(profile_id=profile_id, name=name, provider=provider,
                             base_url=base_url, model=model)
        if previous and previous.key_slot != profile.key_slot:
            keys.pop(previous.key_slot, None)
        if api_key and api_key.strip():
            keys[profile.key_slot] = api_key.strip()
        message = "Đã nhập key cho phiên này." if keys.get(profile.key_slot) else "Chưa có API key."
        return profile.id, "", message, keys
    except ValueError as error:
        return profile_id, "", str(error), keys


def clear_profile_key(profile_id, keys, store=PROFILE_STORE):
    keys = dict(keys or {})
    profile = next((item for item in store.read().profiles if item.id == profile_id), None)
    if profile:
        keys.pop(profile.key_slot, None)
    return keys


def _load_profile(profile_id, keys, store):
    try:
        profile = next((item for item in store.read().profiles if item.id == profile_id), None)
    except ValueError as error:
        return "", "custom", "", "", str(error), "", False
    if not profile:
        return "", "custom", "", "", "Chưa có kết nối API.", "", False
    status = "Đã nhập key cho phiên này." if (keys or {}).get(profile.key_slot) else "Chưa có API key."
    return profile.name, profile.provider, profile.base_url, profile.model, status, "", True


def _probe_generation(session_hash):
    if not session_hash:
        return None
    with _PROBE_LOCK:
        return _PROBE_GENERATIONS.get(session_hash, 0)


def _reset_connection_status(request: gr.Request):
    with _PROBE_LOCK:
        session_hash = request.session_hash
        _PROBE_GENERATIONS[session_hash] = _PROBE_GENERATIONS.get(session_hash, 0) + 1
    return "Chưa kiểm tra kết nối."


def _connection_status(profile_id, keys, store, provider=None, base_url=None, model=None,
                       session_hash=None):
    try:
        generation = _probe_generation(session_hash)
        profile = next((item for item in store.read().profiles if item.id == profile_id), None)
        if not profile:
            return "Kết nối đã bị xóa. Tải lại danh sách rồi thử lại."
        if (provider, base_url.strip(), model.strip()) != (profile.provider, profile.base_url, profile.model):
            return "Lưu cấu hình hiện tại trước khi kiểm tra kết nối."
        key = (keys or {}).get(profile.key_slot)
        if not key:
            return "Nhập và lưu API key của kết nối này trước khi kiểm tra."
        validate_base_url(profile.base_url)
        result = check_connection(profile.base_url, profile.model, key)
        latest = next((item for item in store.read().profiles if item.id == profile_id), None)
        if latest != profile or generation != _probe_generation(session_hash):
            return "Cấu hình đã thay đổi trong lúc kiểm tra. Hãy kiểm tra lại."
        return "Kết nối thành công." if result == "ok" else ERRORS.get(result, ERRORS["backend"])
    except ValueError as error:
        return str(error)


def _set_provider(provider):
    base_url, model = PROVIDER_DEFAULTS.get(provider, PROVIDER_DEFAULTS["custom"])
    return base_url, model


def translate_ui(pdf, base_url, model, api_key, lang_in, lang_out, request: gr.Request,
                 runner=RUNNER, progress=gr.Progress(), *, preview_pages=None):
    yield "Đang kiểm tra PDF và cấu hình…", None, None, gr.update(interactive=False), gr.update(interactive=True)
    status, mono, dual = "Đã dừng tác vụ.", None, None
    try:
        if not pdf:
            raise ValueError("Vui lòng chọn một file PDF.")
        settings = TranslationRequest(str(pdf), base_url.strip(), model.strip(), api_key,
                                      lang_in, lang_out, preview_pages)
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


def _translate_profile_ui(pdf, profile_id, pages, lang_in, lang_out, keys, request: gr.Request,
                          runner=RUNNER, progress=gr.Progress(), store=PROFILE_STORE):
    try:
        profile = next((item for item in store.read().profiles if item.id == profile_id), None)
    except ValueError as error:
        yield str(error), None, None, None, None, gr.update(interactive=True), gr.update(interactive=False)
        return
    if not profile:
        yield "Chọn kết nối API trong Cài đặt API trước khi dịch.", None, None, None, None, gr.update(interactive=True), gr.update(interactive=False)
        return
    key = (keys or {}).get(profile.key_slot)
    if not key:
        yield "Kết nối này chưa có API key. Mở Cài đặt API để nhập key.", None, None, None, None, gr.update(interactive=True), gr.update(interactive=False)
        return
    if pages == "all":
        preview_pages = None
    elif pages in ("1", "2", "3"):
        preview_pages = int(pages)
    else:
        yield "Phạm vi dịch không hợp lệ. Hãy chọn lại phạm vi.", None, None, None, None, gr.update(interactive=True), gr.update(interactive=False)
        return
    for status, mono, dual, start_update, cancel_update in translate_ui(
        pdf, profile.base_url, profile.model, key, lang_in, lang_out, request,
        runner=runner, progress=progress, preview_pages=preview_pages,
    ):
        source_preview = translated_preview = None
        if mono and dual:
            source_path = Path(mono).parents[1] / "input.pdf"
            source_preview = render_first_page(source_path)
            translated_preview = render_first_page(mono)
            scope = "Dịch thử 1 trang" if preview_pages == 1 else f"Dịch thử {preview_pages} trang" if preview_pages else "Đã dịch toàn bộ tài liệu"
            status = f"{status} {scope}."
            if source_preview is None or translated_preview is None:
                status = f"{status} Không thể tạo ảnh xem trước; bạn vẫn có thể tải hai PDF."
        yield status, mono, dual, source_preview, translated_preview, start_update, cancel_update


def _page_choices(pdf):
    if not pdf:
        return gr.update(choices=[("Toàn bộ tài liệu", "all")], value="all"), "Chọn tài liệu PDF để xem số trang."
    try:
        count = pdf_page_count(pdf)
    except ValueError as error:
        return gr.update(choices=[("Toàn bộ tài liệu", "all")], value="all"), str(error)
    choices = [("Toàn bộ tài liệu", "all")]
    choices.extend((f"Dịch thử {pages} trang đầu", str(pages)) for pages in range(1, min(3, count) + 1))
    return gr.update(choices=choices, value="all"), f"Tài liệu có {count} trang."


def _profile_changes(store):
    try:
        catalog = store.read()
        choices = [(f"{profile.name}{' · Mặc định' if profile.id == catalog.default_id else ''}", profile.id)
                   for profile in catalog.profiles]
        selected = catalog.default_id or (catalog.profiles[0].id if catalog.profiles else None)
    except ValueError:
        choices, selected = [], None
    return gr.update(choices=choices, value=selected), gr.update(choices=choices, value=selected)


def _profile_list(store):
    try:
        catalog = store.read()
        return [(f"{profile.name}{' · Mặc định' if profile.id == catalog.default_id else ''}", profile.id)
                for profile in catalog.profiles]
    except ValueError:
        return []


def _clear_results():
    return None, None, None, None, "Sẵn sàng. Chọn phạm vi dịch."


def _is_insecure_external_url(value):
    try:
        parsed = urlsplit(value.strip())
        hostname = parsed.hostname
        if parsed.scheme != "http" or not hostname or hostname.lower() == "localhost":
            return False
        try:
            return not ipaddress.ip_address(hostname).is_loopback
        except ValueError:
            return True
    except ValueError:
        return False


def build_app(*, store: ProfileStore | None = None):
    store = store or PROFILE_STORE
    try:
        catalog = store.read()
        catalog_error = ""
    except ValueError as error:
        catalog = ProfileCatalog((), None)
        catalog_error = str(error)
    choices = [(f"{profile.name}{' · Mặc định' if profile.id == catalog.default_id else ''}", profile.id)
               for profile in catalog.profiles]
    selected = catalog.default_id or (catalog.profiles[0].id if catalog.profiles else None)
    initial_name, initial_provider, initial_url, initial_model, initial_key_status, _, _ = _load_profile(
        selected, {}, store) if selected else ("", "custom", "", "", "Chưa có kết nối API.", "", False)
    css = (Path(__file__).with_name("ui.css").read_text(encoding="utf-8")
           if Path(__file__).with_name("ui.css").exists() else "")
    with gr.Blocks(title="TransDocument", theme=gr.themes.Soft(primary_hue="green", neutral_hue="stone"),
                   analytics_enabled=False, css=css, fill_width=True) as app:
        keys = gr.State({})
        with gr.Row(elem_classes="td-header"):
            gr.Markdown("## TransDocument", elem_classes="td-brand")
            gr.Markdown("Dịch PDF · Chạy trên máy của bạn", elem_classes="td-tagline")
        with gr.Tabs():
            with gr.Tab("Dịch tài liệu", id="translate"):
                gr.Markdown("# Dịch tài liệu\nChọn PDF, cấu hình ngôn ngữ và chạy thử trước khi dịch toàn bộ.")
                with gr.Row(elem_classes="td-workspace"):
                    with gr.Column(scale=1, min_width=280, elem_classes="td-form-column"):
                        pdf = gr.File(label="Tài liệu PDF", file_types=[".pdf"], type="filepath", file_count="single")
                        page_info = gr.Markdown("Chọn tài liệu PDF để xem số trang.")
                        pages = gr.Dropdown([( "Toàn bộ tài liệu", "all")], value="all", label="Phạm vi dịch")
                        with gr.Row(elem_classes="td-languages"):
                            lang_in = gr.Dropdown(LANGUAGES, value="en", label="Ngôn ngữ nguồn")
                            lang_out = gr.Dropdown(LANGUAGES, value="vi", label="Ngôn ngữ đích")
                        job_profile = gr.Dropdown(choices, value=selected, label="Kết nối API")
                        gr.Markdown("Văn bản PDF được gửi đến dịch vụ API bạn chọn. Lần chạy đầu có thể tải model bố cục và font.")
                        with gr.Row(elem_classes="td-downloads"):
                            start = gr.Button("Dịch PDF", variant="primary", elem_classes="td-primary")
                            cancel = gr.Button("Hủy", interactive=False)
                        status = gr.Textbox(label="Trạng thái", value="Sẵn sàng. Chọn PDF và kết nối API.",
                                            interactive=False, lines=2, elem_classes="td-status")
                    with gr.Column(scale=2, min_width=300, elem_classes="td-result-column"):
                        gr.Markdown("## Kết quả")
                        with gr.Row(elem_classes="td-previews"):
                            source_preview = gr.Image(label="Bản gốc · trang đầu", interactive=False, type="pil")
                            translated_preview = gr.Image(label="Bản dịch · trang đầu", interactive=False, type="pil")
                        with gr.Row():
                            mono = gr.File(label="PDF bản dịch", interactive=False)
                            dual = gr.File(label="PDF song ngữ", interactive=False)
                pdf.change(_page_choices, inputs=pdf, outputs=[pages, page_info], queue=False, api_name=False)
                pdf.change(_clear_results, outputs=[source_preview, translated_preview, mono, dual, status], queue=False, api_name=False)
                start.click(
                    lambda *args: _translate_profile_ui(*args, store=store),
                    inputs=[pdf, job_profile, pages, lang_in, lang_out, keys],
                    outputs=[status, mono, dual, source_preview, translated_preview, start, cancel],
                    concurrency_limit=None, api_name=False,
                )
                cancel.click(cancel_ui, outputs=status, queue=False, api_name=False)
                app.unload(disconnect)

            with gr.Tab("Cài đặt API", id="settings"):
                gr.Markdown("# Cài đặt API\nQuản lý kết nối và API key trong phiên trình duyệt này.")
                with gr.Row(elem_classes="td-settings-workspace"):
                    with gr.Column(scale=1, min_width=220):
                        api_profile = gr.Dropdown(choices, value=selected, label="Kết nối của bạn", interactive=True)
                        add = gr.Button("Thêm kết nối")
                        default_btn = gr.Button("Đặt làm mặc định")
                        delete_btn = gr.Button("Xóa kết nối", elem_classes="td-danger")
                        with gr.Row(visible=False) as delete_confirm:
                            gr.Markdown("Xóa kết nối này?")
                            confirm_delete = gr.Button("Xóa", elem_classes="td-danger")
                            keep_profile = gr.Button("Giữ lại")
                    with gr.Column(scale=2, min_width=300, elem_classes="td-settings-panel"):
                        gr.Markdown("## Thông tin kết nối")
                        profile_id = gr.Textbox(value=selected or "", visible=False)
                        profile_name = gr.Textbox(label="Tên kết nối", value=initial_name, max_lines=1,
                                                  placeholder="Ví dụ: Gemini cá nhân")
                        provider = gr.Dropdown(PROVIDERS, value=initial_provider, label="Dịch vụ")
                        base_url = gr.Textbox(label="Base URL", value=initial_url, placeholder="https://api.example.com/v1/")
                        http_warning = gr.Markdown("HTTP ngoài máy này không mã hóa API key. Ưu tiên HTTPS.",
                                                    visible=_is_insecure_external_url(initial_url))
                        model = gr.Textbox(label="Model", value=initial_model)
                        api_key = gr.Textbox(label="API key", type="password", value="",
                                             placeholder="Nhập key, không lưu vào file cấu hình")
                        key_status = gr.Markdown(initial_key_status)
                        with gr.Row():
                            save_btn = gr.Button("Lưu kết nối", variant="primary")
                            clear_key_btn = gr.Button("Xóa key khỏi phiên")
                            test_btn = gr.Button("Kiểm tra kết nối")
                        connection_status = gr.Markdown(catalog_error or "Chưa kiểm tra kết nối.")
                        gr.Markdown("Kiểm tra gửi yêu cầu dịch ngắn Hello và có thể tính vào quota của dịch vụ.")

                def load_profile(profile_id_value, session_keys):
                    result = _load_profile(profile_id_value, session_keys, store)
                    return (profile_id_value or "", *result[:6], gr.update(interactive=bool(profile_id_value)),
                            gr.update(visible=_is_insecure_external_url(result[2])))

                def save_and_refresh(profile_id_value, name, provider_value, url, model_value, key_value, session_keys):
                    result = save_profile(profile_id_value, name, provider_value, url, model_value,
                                          key_value, session_keys, store)
                    return result

                def remove_profile(profile_id_value, session_keys):
                    try:
                        catalog_before = store.read()
                        profile = next((item for item in catalog_before.profiles if item.id == profile_id_value), None)
                        store.delete(profile_id_value)
                        state = dict(session_keys or {})
                        if profile:
                            state.pop(profile.key_slot, None)
                        updates = _profile_changes(store)
                        return (*updates, state, "Kết nối đã được xóa.")
                    except ValueError as error:
                        return (*_profile_changes(store), session_keys or {}, str(error))

                def run_connection_probe(current_id, session_keys, service, url, model_name,
                                         request: gr.Request):
                    return _connection_status(current_id, session_keys, store, service, url,
                                              model_name, request.session_hash)

                api_profile.change(
                    load_profile,
                    inputs=[api_profile, keys],
                    outputs=[profile_id, profile_name, provider, base_url, model, key_status, api_key, default_btn,
                             http_warning],
                    queue=False, api_name=False,
                ).then(_reset_connection_status, outputs=connection_status, queue=False, api_name=False)
                provider.change(_set_provider, inputs=provider, outputs=[base_url, model], queue=False, api_name=False)
                provider.change(_reset_connection_status, outputs=connection_status, queue=False, api_name=False)
                model.change(_reset_connection_status, outputs=connection_status, queue=False, api_name=False)
                api_key.change(_reset_connection_status, outputs=connection_status, queue=False, api_name=False)
                base_url.change(
                    lambda value: gr.update(visible=_is_insecure_external_url(value)),
                    inputs=base_url, outputs=http_warning, queue=False, api_name=False,
                ).then(_reset_connection_status, outputs=connection_status, queue=False, api_name=False)
                add.click(
                    lambda: ("", "custom", "", "", "Chưa có API key.", "", gr.update(interactive=False), "Thêm kết nối mới."),
                    outputs=[profile_id, provider, base_url, model, key_status, api_key, default_btn, connection_status],
                    queue=False, api_name=False,
                ).then(lambda: ("", ""), outputs=[profile_name, api_key], queue=False, api_name=False
                ).then(_reset_connection_status, outputs=connection_status, queue=False, api_name=False)
                save_btn.click(
                    save_and_refresh,
                    inputs=[profile_id, profile_name, provider, base_url, model, api_key, keys],
                    outputs=[profile_id, api_key, key_status, keys], queue=False, api_name=False,
                ).then(lambda profile_id_value: (gr.update(choices=_profile_list(store), value=profile_id_value),
                                                  gr.update(choices=_profile_list(store), value=profile_id_value),
                                                  "Chưa kiểm tra kết nối."),
                       inputs=profile_id,
                       outputs=[api_profile, job_profile, connection_status], queue=False, api_name=False
                ).then(_reset_connection_status, outputs=connection_status, queue=False, api_name=False)
                default_btn.click(
                    lambda profile_id_value: _set_default_profile(profile_id_value, store),
                    inputs=profile_id, outputs=[api_profile, job_profile, connection_status],
                    queue=False, api_name=False,
                ).then(_reset_connection_status, outputs=connection_status, queue=False, api_name=False)
                clear_key_btn.click(
                    lambda profile_id_value, session_keys: (
                        clear_profile_key(profile_id_value, session_keys, store), "", "Chưa có API key.",
                        "Key đã được xóa khỏi phiên này.",
                    ),
                    inputs=[profile_id, keys], outputs=[keys, api_key, key_status, connection_status],
                    queue=False, api_name=False,
                ).then(_reset_connection_status, outputs=connection_status, queue=False, api_name=False)
                test_btn.click(run_connection_probe,
                               inputs=[profile_id, keys, provider, base_url, model], outputs=connection_status,
                               queue=False, api_name=False)
                delete_btn.click(lambda: gr.update(visible=True), outputs=delete_confirm, queue=False, api_name=False)
                keep_profile.click(lambda: gr.update(visible=False), outputs=delete_confirm, queue=False, api_name=False)
                confirm_delete.click(
                    remove_profile, inputs=[profile_id, keys],
                    outputs=[api_profile, job_profile, keys, connection_status], queue=False, api_name=False,
                ).then(load_profile, inputs=[api_profile, keys],
                       outputs=[profile_id, profile_name, provider, base_url, model, key_status, api_key, default_btn,
                                http_warning],
                       queue=False, api_name=False).then(_reset_connection_status, outputs=connection_status,
                                                          queue=False, api_name=False)

    return app.queue(default_concurrency_limit=1, max_size=8)


def _set_default_profile(profile_id, store):
    try:
        store.set_default(profile_id)
        updates = _profile_changes(store)
        return (*updates, "Kết nối mặc định đã được cập nhật.")
    except ValueError as error:
        updates = _profile_changes(store)
        return (*updates, str(error))


def cancel_ui(request: gr.Request):
    if RUNNER.cancel(request.session_hash):
        return "Đang hủy tiến trình dịch…"
    return "Không có tác vụ đang chạy trong phiên của bạn."


def disconnect(request: gr.Request):
    _reset_connection_status(request)
    RUNNER.cancel(request.session_hash)


def main():
    multiprocessing.freeze_support()
    app = build_app()
    app.launch(server_name="127.0.0.1", server_port=7860, share=False,
               inbrowser=True, show_error=False, show_api=False)


if __name__ == "__main__":
    main()
