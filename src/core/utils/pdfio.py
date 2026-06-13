"""PDF input — render PDF pages to PIL images so they enter the normal pipeline.

A PDF Source is treated as a stack of page images: each page becomes its own
Job (rendered at PDF_DPI), so the Sectioned Scan, Boost Queue and Shared Store
all work unchanged. Rendering uses pypdfium2 (bundled PDFium — no external
program needed, works offline and inside a frozen .exe).
"""
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image

PDF_DPI = 400            # deep-detail render (Nick: slower is fine); A4 ≈ 3307x4677 px
MAX_PAGE_PIXELS = 80_000_000  # safety cap for huge pages (A0 drawings) — scale down, never crash


def is_pdf(path: str | Path) -> bool:
    """True when the file should go through the PDF door."""
    return Path(path).suffix.lower() == ".pdf"


def page_count(path: str | Path) -> int:
    """Number of pages without rendering anything."""
    pdf = pdfium.PdfDocument(str(path))
    try:
        return len(pdf)
    finally:
        pdf.close()


def page_size_mm(path: str | Path, index: int) -> tuple[float, float]:
    """Physical page size (width_mm, height_mm) WITHOUT rendering — measured
    before every scan so the Sectioned-Scan grid is computed from the real
    paper size (A4 vs A0), not from arbitrary pixel counts (Nick, v0.1.5)."""
    pdf = pdfium.PdfDocument(str(path))
    try:
        page = pdf[index]
        w_pt, h_pt = page.get_size()
        page.close()
        return (w_pt / 72.0 * 25.4, h_pt / 72.0 * 25.4)
    finally:
        pdf.close()


def render_page(path: str | Path, index: int, dpi: int = PDF_DPI) -> Image.Image:
    """Render one page (0-based) to a grayscale-friendly RGB image."""
    pdf = pdfium.PdfDocument(str(path))
    try:
        return _render(pdf, index, dpi)
    finally:
        pdf.close()


def _render(pdf, index: int, dpi: int) -> Image.Image:
    page = pdf[index]
    scale = dpi / 72.0  # PDF user space is 72 units per inch
    w, h = page.get_size()
    if (w * scale) * (h * scale) > MAX_PAGE_PIXELS:
        scale = (MAX_PAGE_PIXELS / (w * h)) ** 0.5
    img = page.render(scale=scale).to_pil().convert("RGB")
    page.close()
    return img


class PdfReader:
    """Open a PDF once and read every page from the same handle — a 45-page,
    16 MB drawing used to be opened/parsed ~91 times (page_count + size + render
    each reopened the file), which lengthened the perceived 'hang'. Use as a
    context manager so the handle is always closed (v0.2.0)."""

    def __init__(self, path: str | Path):
        self._pdf = pdfium.PdfDocument(str(path))

    def __enter__(self) -> "PdfReader":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def __len__(self) -> int:
        return len(self._pdf)

    def page_count(self) -> int:
        return len(self._pdf)

    def page_size_mm(self, index: int) -> tuple[float, float]:
        page = self._pdf[index]
        w_pt, h_pt = page.get_size()
        page.close()
        return (w_pt / 72.0 * 25.4, h_pt / 72.0 * 25.4)

    def render_page(self, index: int, dpi: int = PDF_DPI) -> Image.Image:
        return _render(self._pdf, index, dpi)

    def close(self) -> None:
        self._pdf.close()
