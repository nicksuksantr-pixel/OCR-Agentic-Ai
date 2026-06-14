"""Headless smoke test for the inbox watcher — drop a file, expect a Job.

Uses a short poll interval and a real (tiny) image so the whole loop runs:
stability check → scan → move to inbox\\processed → job in the Shared Store.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import os as _os, tempfile as _tempfile  # noqa: E402 — isolate the test store
# Own data dir (NOT the shared "ocr-agentic-tests"): the watcher owns the inbox
# tree, so sharing it with sibling suites run back-to-back let a still-running
# poll loop race their cleanup → "[WinError 2]" mid-move. Combined with stop()+
# join() below, this suite is fully isolated.
_os.environ.setdefault("OCR_AGENTIC_DATA_DIR",
                       str(Path(_tempfile.gettempdir()) / "ocr-agentic-tests-watcher"))

sys.stdout.reconfigure(encoding="utf-8")

from PIL import Image, ImageDraw, ImageFont

from src.core.config import paths
from src.core.config import settings as settings_mod
from src.core.services import engine
from src.features.watcher import service as watcher_service
from src.features.watcher.service import InboxWatcher


def main() -> None:
    paths.ensure_dirs()
    settings = settings_mod.load()
    err = engine.configure(settings)
    if err:
        print("ENGINE ERROR:", err)
        sys.exit(1)

    img = Image.new("L", (900, 300), 255)
    d = ImageDraw.Draw(img)
    d.text((30, 100), "INBOX WATCHER TEST PUMP P-300", font=ImageFont.truetype("arial.ttf", 36), fill=0)
    dropped = paths.INBOX_DIR / "smoke_watcher_drop.png"
    img.save(dropped)

    watcher_service.POLL_SECONDS = 0.5  # fast loop for the test
    done = {}
    watcher = InboxWatcher(settings, on_event=lambda m: print(" ", m),
                           on_job_done=lambda res: done.update(job=res))
    watcher.start()
    deadline = time.time() + 300  # deep-detail mode scans slowly on purpose (Nick's order)
    while not done and time.time() < deadline:
        time.sleep(0.3)
    watcher.stop()
    watcher.join()  # let the in-flight _process()/_move() finish before asserting (no race)

    checks = {
        "job produced": bool(done),
        "text found": bool(done and "P-300" in done["job"].full_text),
        "inbox emptied": not dropped.exists(),
        "moved to processed": any(p.name.startswith("smoke_watcher_drop")
                                  for p in paths.INBOX_PROCESSED.iterdir()),
    }
    print()
    for name, ok in checks.items():
        print(("✅" if ok else "❌"), name)
    sys.exit(0 if all(checks.values()) else 1)


if __name__ == "__main__":
    main()
