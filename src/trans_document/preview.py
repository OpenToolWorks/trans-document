"""Small first-page previews for the translation result panel."""

from pathlib import Path

import pymupdf
from PIL import Image


def render_first_page(path: str | Path) -> Image.Image | None:
    try:
        with pymupdf.open(path) as document:
            if not document.is_pdf or document.needs_pass or not document.page_count:
                return None
            page = document[0]
            scale = min(1, 1200 / max(page.rect.width, page.rect.height))
            pixmap = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
            return pixmap.pil_image().convert("RGB")
    except Exception:
        return None
