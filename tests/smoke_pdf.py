"""Headless smoke test for PDF input — build a 2-page PDF, run run_source, verify.

Offline, no Gemini. Checks: one Job per page, page/pages recorded in result.json,
rendered original.png saved, and the expected words actually recognized.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

from PIL import Image, ImageDraw, ImageFont

from src.core.config import paths
from src.core.config import settings as settings_mod
from src.core.services import engine
from src.core.utils import pdfio
from src.features.scan import service

PAGE_TEXTS = ["PUMP ROOM PANEL 220V", "ENGINE ROOM FEEDER 440V"]


def make_test_pdf(path: Path) -> None:
    """Two simple pages with big English text (PIL writes multi-page PDFs natively)."""
    Image.init()  # force-load all plugins — PDF saving needs the JPEG encoder registered
    font = ImageFont.truetype("arial.ttf", 48)
    pages = []
    for text in PAGE_TEXTS:
        img = Image.new("RGB", (1000, 700), "white")
        d = ImageDraw.Draw(img)
        d.text((60, 80), text, font=font, fill="black")
        d.rectangle((40, 60, 960, 640), outline="black", width=2)
        pages.append(img)
    pages[0].save(path, save_all=True, append_images=pages[1:], resolution=150)


def check(ok: bool, label: str) -> bool:
    print(("✅" if ok else "❌"), label)
    return ok


def main() -> None:
    paths.ensure_dirs()
    settings = settings_mod.load()
    err = engine.configure(settings)
    if err:
        print("ENGINE ERROR:", err)
        sys.exit(1)

    pdf_path = paths.DATA_DIR / "smoke_test.pdf"
    make_test_pdf(pdf_path)

    all_ok = check(pdfio.is_pdf(pdf_path), "is_pdf detects .pdf")
    all_ok &= check(pdfio.page_count(pdf_path) == 2, "page_count == 2")

    results = service.run_source(str(pdf_path), settings,
                                 on_progress=lambda m: print(" ", m))
    all_ok &= check(len(results) == 2, "one Job per page (2 jobs)")
    for i, r in enumerate(results):
        expected = PAGE_TEXTS[i].split()[0]  # first word is plenty for a smoke check
        all_ok &= check(expected in r.full_text,
                        f"page {i + 1} text contains '{expected}' (conf {r.mean_conf}%)")
        all_ok &= check(r.page == i + 1 and r.pages == 2, f"page {i + 1} numbering on JobResult")
        all_ok &= check((Path(r.job_dir) / "original.png").exists(),
                        f"page {i + 1} rendered original.png saved")
        payload = json.loads((Path(r.job_dir) / "result.json").read_text(encoding="utf-8"))
        all_ok &= check(payload.get("page") == i + 1 and payload.get("pages") == 2,
                        f"page {i + 1} result.json has additive page/pages fields")
        all_ok &= check(f"#page={i + 1}" in payload["source_path"],
                        f"page {i + 1} source recorded as path#page=N")

    print("\nPDF SMOKE:", "PASS" if all_ok else "FAIL")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
