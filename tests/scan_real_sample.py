"""Real-file sample runner — scan selected pages of a PDF through the full
deep-detail pipeline. Usage:

    python tests\\scan_real_sample.py <pdf_path> <page,page,...>

One Job per page, exactly like production; prints a quality report per page.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import os as _os, tempfile as _tempfile  # noqa: E402 — isolate the test store
_os.environ.setdefault("OCR_AGENTIC_DATA_DIR",
                       str(Path(_tempfile.gettempdir()) / "ocr-agentic-tests"))

sys.stdout.reconfigure(encoding="utf-8")

from src.core.config import paths
from src.core.config import settings as settings_mod
from src.core.services import engine
from src.core.utils import pdfio
from src.features.scan import service


def main() -> None:
    pdf = sys.argv[1]
    pages = [int(p) for p in sys.argv[2].split(",")]
    paths.ensure_dirs()
    settings = settings_mod.load()
    err = engine.configure(settings)
    if err:
        print("ENGINE ERROR:", err)
        sys.exit(1)
    total = pdfio.page_count(pdf)
    print(f"source: {pdf} ({total} pages) — sampling pages {pages}", flush=True)

    for p in pages:
        t0 = time.time()
        img = pdfio.render_page(pdf, p - 1)
        result = service.run_job(
            f"{pdf}#page={p}", settings,
            on_progress=lambda m, p=p: print(f"  p{p}: {m}", flush=True),
            image=img, page=p, pages=total)
        secs = round(time.time() - t0)
        queued = sum(1 for s in result.sections if s.status in ("low_conf", "unreadable"))
        rescued = [(s.idx, s.rescue_method) for s in result.sections if s.rescued]
        print(f"\n=== PAGE {p} → job {result.job_id} | {secs}s | "
              f"conf {result.mean_conf}% | words {len(result.words)} | "
              f"sections {len(result.sections)} | queued {queued} | rescued {rescued}")
        preview = "\n".join(result.full_text.splitlines()[:25])
        print(preview, "\n", flush=True)


if __name__ == "__main__":
    main()
