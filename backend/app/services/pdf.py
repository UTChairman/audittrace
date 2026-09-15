from dataclasses import dataclass
from pathlib import Path

import pymupdf

from app.config import PAGES_DIR, get_settings


class PdfProcessingError(Exception):
    """Raised when a PDF cannot be processed."""


@dataclass(frozen=True)
class RenderedPage:
    page_number: int
    image_path: Path
    width_px: int
    height_px: int


def _render_page(page: pymupdf.Page, page_number: int, output_dir: Path) -> RenderedPage:
    zoom = 200 / 72
    matrix = pymupdf.Matrix(zoom, zoom)
    pixmap = page.get_pixmap(matrix=matrix, alpha=False)
    output_dir.mkdir(parents=True, exist_ok=True)
    image_path = output_dir / f"page_{page_number}.png"
    pixmap.save(str(image_path))
    return RenderedPage(
        page_number=page_number,
        image_path=image_path,
        width_px=pixmap.width,
        height_px=pixmap.height,
    )


def render_pdf_to_pages(pdf_bytes: bytes, document_id: int) -> list[RenderedPage]:
    settings = get_settings()
    output_dir = PAGES_DIR / str(document_id)

    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
        page_count = doc.page_count
        if page_count > settings.max_pdf_pages:
            raise PdfProcessingError(
                f"PDF has {page_count} pages; maximum allowed is {settings.max_pdf_pages}"
            )
        return [
            _render_page(doc.load_page(index), index + 1, output_dir)
            for index in range(page_count)
        ]


def render_image_page(image_bytes: bytes, document_id: int, suffix: str = "png") -> list[RenderedPage]:
    output_dir = PAGES_DIR / str(document_id)
    output_dir.mkdir(parents=True, exist_ok=True)
    image_path = output_dir / f"page_1.{suffix}"
    image_path.write_bytes(image_bytes)

    with pymupdf.open(stream=image_bytes, filetype=suffix) as doc:
        page = doc.load_page(0)
        rect = page.rect
        width_px = int(rect.width) or 1
        height_px = int(rect.height) or 1

    return [
        RenderedPage(
            page_number=1,
            image_path=image_path,
            width_px=width_px,
            height_px=height_px,
        )
    ]
