"""One session-owned PDF translation at a time, isolated in a spawned worker."""

import contextlib
import multiprocessing
import shutil
import threading
import uuid
from dataclasses import dataclass, field, replace
from pathlib import Path

import pymupdf

from .profiles import validate_base_url
from .worker import translate_worker


@dataclass(frozen=True)
class TranslationRequest:
    pdf_path: str
    base_url: str
    model: str
    api_key: str = field(repr=False)
    lang_in: str = "en"
    lang_out: str = "vi"
    preview_pages: int | None = None

    def validate(self):
        validate_base_url(self.base_url)
        if not self.model.strip() or not self.api_key.strip():
            raise ValueError("Vui lòng nhập model và API key.")
        if not self.lang_in or not self.lang_out or self.lang_in == self.lang_out:
            raise ValueError("Chọn hai ngôn ngữ khác nhau.")
        page_count = pdf_page_count(self.pdf_path)
        if self.preview_pages is not None and (
            isinstance(self.preview_pages, bool) or not isinstance(self.preview_pages, int)
            or not 1 <= self.preview_pages <= 3
            or self.preview_pages > page_count
        ):
            raise ValueError("Chọn từ 1 đến 3 trang đầu và không vượt số trang trong PDF.")


def _check_pdf(path):
    try:
        with pymupdf.open(path) as document:
            if not document.is_pdf or document.needs_pass or document.page_count < 1:
                raise ValueError
            return document.page_count
    except Exception:
        raise ValueError("PDF không hợp lệ, trống hoặc có mật khẩu.") from None


def pdf_page_count(path):
    return _check_pdf(path)


@dataclass
class _ActiveJob:
    owner: str
    process: object
    cancelled: threading.Event = field(default_factory=threading.Event)


class JobRunner:
    def __init__(self, output_root, worker=translate_worker):
        self.output_root = Path(output_root).resolve()
        self.worker = worker
        self._lock = threading.Lock()
        self._active = None

    def stream(self, request, owner):
        request.validate()
        if not owner:
            raise ValueError("Không xác định được phiên trình duyệt; hãy tải lại trang.")
        context = multiprocessing.get_context("spawn")
        recv, send = context.Pipe(duplex=False)
        job_dir = self.output_root / uuid.uuid4().hex
        output_dir = job_dir / "result"
        job = None
        success = False
        try:
            with self._lock:
                if self._active is not None:
                    raise ValueError("Có tác vụ đang chạy; hãy đợi hoặc hủy tác vụ của bạn.")
                output_dir.mkdir(parents=True)
                source = job_dir / "input.pdf"
                shutil.copyfile(request.pdf_path, source)
                process = context.Process(
                    target=self.worker,
                    args=(replace(request, pdf_path=str(source)), str(output_dir), send),
                )
                job = _ActiveJob(owner, process)
                process.start()
                self._active = job
            send.close()
            yield {"type": "progress", "stage": "Khởi tạo BabelDOC / tải model và font", "percent": 0}
            while True:
                if job.cancelled.is_set():
                    yield {"type": "cancelled"}
                    return
                if not recv.poll(0.2):
                    if not process.is_alive():
                        yield {"type": "error", "code": "worker"}
                        return
                    continue
                try:
                    event = recv.recv()
                except (EOFError, OSError):
                    yield {"type": "error", "code": "worker"}
                    return
                if job.cancelled.is_set():
                    yield {"type": "cancelled"}
                    return
                if event.get("type") == "finish":
                    try:
                        paths = [Path(event[key]).resolve() for key in ("mono", "dual")]
                        if not all(path.is_relative_to(output_dir.resolve()) for path in paths):
                            raise ValueError
                        for path in paths:
                            _check_pdf(path)
                    except (ValueError, KeyError, TypeError):
                        yield {"type": "error", "code": "output"}
                        return
                    success = True
                    yield {"type": "finish", "mono": str(paths[0]), "dual": str(paths[1]),
                           "source": str(source)}
                    return
                if event.get("type") == "error":
                    code = event.get("code")
                    yield {"type": "error", "code": code if code in {
                        "authentication", "quota", "connection", "pdf", "backend"
                    } else "backend"}
                    return
                if event.get("type") == "progress":
                    yield event
        finally:
            if job is not None:
                with self._lock:
                    with contextlib.suppress(ValueError, OSError):
                        if job.process.is_alive():
                            job.process.terminate()
                        job.process.join(timeout=3)
                        if job.process.is_alive():
                            job.process.kill()
                            job.process.join(timeout=2)
                        job.process.close()
                    if self._active is job:
                        self._active = None
            recv.close()
            send.close()
            if not success:
                shutil.rmtree(job_dir, ignore_errors=True)

    def cancel(self, owner):
        with self._lock:
            job = self._active
            if job is None or job.owner != owner:
                return False
            job.cancelled.set()
            with contextlib.suppress(ValueError, OSError):
                job.process.terminate()
            return True

    def shutdown(self):
        with self._lock:
            owner = self._active.owner if self._active else None
        if owner:
            self.cancel(owner)
