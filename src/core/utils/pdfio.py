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


def render_page(path: str | Path, index: int, dpi: int = PDF_DPI) -> Image.Image:
    """Render one page (0-based) to a grayscale-friendly RGB image."""
    pdf = pdfium.PdfDocument(str(path))
    try:
        page = pdf[index]
        scale = dpi / 72.0  # PDF user space is 72 units per inch
        w, h = page.get_size()
        if (w * scale) * (h * scale) > MAX_PAGE_PIXELS:
            scale = (MAX_PAGE_PIXELS / (w * h)) ** 0.5
        img = page.render(scale=scale).to_pil().convert("RGB")
        page.close()
        return img
    finally:
        pdf.close()
