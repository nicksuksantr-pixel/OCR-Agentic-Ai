"""Headless smoke test for v0.1.3: auto language detect, batch resume, orphan
cleanup, updater version logic. Touches ONLY rows it creates."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import os as _os, tempfile as _tempfile  # noqa: E402 — isolate the test store
_os.environ.setdefault("OCR_AGENTIC_DATA_DIR",
                       str(Path(_tempfile.gettempdir()) / "ocr-agentic-tests"))

sys.stdout.reconfigure(encoding="utf-8")

from src.core.config import paths
from src.core.models.ocr import Word
from src.core.services import store
from src.features.scan.service import latin_only_page
from src.features.updater.service import parse_version


def w(text: str, conf: float = 90.0) -> Word:
    return Word(text, conf, 0, 0, 10, 10)


def main() -> None:
    checks: dict[str, bool] = {}

    # --- latin_only_page heuristics ---
    noise_page = [w("MAIN"), w("SWITCHBOARD"), w("440V"), w("BREAKER"), w("CB-101"),
                  w("ง"), w("เ"), w("ผ"), w("ท า"), w("เพ")] + [w(f"WORD{i}") for i in range(40)]
    checks["glyph noise page → eng only"] = latin_only_page(noise_page) is True

    thai_page = ([w("ตู้ไฟหลัก"), w("เครื่องกำเนิดไฟฟ้า"), w("สวิตช์บอร์ด"), w("แรงดันไฟ")]
                 + [w(f"W{i}") for i in range(20)])
    checks["real Thai page keeps tha"] = latin_only_page(thai_page) is False

    checks["empty page keeps tha"] = latin_only_page([]) is False
    low_conf_thai = [w("ASD"), w("ตู้ไฟหลักจริง", conf=30.0)]
    checks["low-conf Thai ignored"] = latin_only_page(low_conf_thai) is True

    # --- batch resume: done_pages ---
    paths.ensure_dirs()
    src = "C:/fake/smoke_lang_resume.pdf"
    ids = []
    for page in (1, 2, 5):
        jid = store.create_job(f"{src}#page={page}", str(paths.JOBS_DIR / "x"), "tha+eng")
        store.finish_job(jid, "text", 80.0)
        ids.append(jid)
    stuck = store.create_job(f"{src}#page=6", str(paths.JOBS_DIR / "x"), "tha+eng")
    checks["done_pages finds finished pages"] = store.done_pages(src) == {1, 2, 5}

    # --- orphan cleanup ---
    closed = store.fail_orphans()
    job = store.get_job(stuck)
    checks["orphan marked error"] = job["status"] == "error" and closed >= 1
    checks["done jobs untouched"] = store.get_job(ids[0])["status"] == "done"
    # tidy: archive the seeded rows out of the visible list (folders never existed)
    for jid in ids + [stuck]:
        store.set_archived(jid, str(paths.JOBS_DIR / "_trash" / "x"))

    # --- updater version compare ---
    checks["version compare"] = (parse_version("v0.1.3") > parse_version("v0.1.2")
                                 and parse_version("v0.1.10") > parse_version("v0.1.9")
                                 and parse_version("v0.1.2") <= parse_version("v0.1.2"))

    print()
    failed = [name for name, ok in checks.items() if not ok]
    for name, ok in checks.items():
        print(("✅" if ok else "❌"), name)
    print(f"\nLANG SMOKE: {'FAIL' if failed else 'PASS'}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
