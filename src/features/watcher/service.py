"""Inbox watcher — polls data\\inbox for dropped Sources and auto-scans them.

Polling (not OS file events) on purpose: dead-simple, no extra dependency, and
immune to the half-written-file problem — a file is only picked up after its
size stays unchanged for one full poll interval (the drop/copy has finished).
After processing the original moves to inbox\\processed (or inbox\\failed) —
moved, never deleted (house rule #6).
"""
import shutil
import threading
import time
from pathlib import Path

from src.core.config import paths
from src.core.config.formats import SUPPORTED_EXT as ALLOWED_EXT  # one shared allow-list (audit P3)
from src.core.config.settings import Settings
from src.core.services import store
from src.features.scan import service as scan_service

POLL_SECONDS = 2.0


class InboxWatcher:
    """Background thread that turns files dropped in inbox\\ into Jobs."""

    def __init__(self, settings: Settings, on_event=lambda msg: None,
                 on_job_done=lambda result: None):
        self.settings = settings
        self.on_event = on_event          # human-readable status line for the UI
        self.on_job_done = on_job_done    # App hook (e.g. auto AI Boost)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._sizes: dict[str, int] = {}  # path -> size seen last poll (stability check)

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True,
                                        name="inbox-watcher")
        self._thread.start()
        self.on_event(f"Watching {paths.INBOX_DIR}")

    def stop(self) -> None:
        self._stop.set()

    def join(self, timeout: float = 15.0) -> None:
        """Block until the worker thread has finished its current cycle and exited.

        For DETERMINISTIC teardown (tests): after stop()+join() no poll loop is
        mid-`_process()`/`_move()`, so the assertions can't race a half-finished
        move and a shared temp dir can't see a file vanish under `shutil.move`.
        The product app deliberately does NOT join on quit — it relies on daemon
        teardown + fail_orphans/resume (the audit's clean-cancel-on-quit item is a
        separate, deferred product change); this helper changes no existing path."""
        t = self._thread
        if t is not None:
            t.join(timeout)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                ready = self._stable_files()
                for f in ready:
                    if self._stop.is_set():
                        break
                    self._process(f)
            except Exception as exc:  # the watcher must survive anything
                self.on_event(f"Watcher error: {exc}")
            self._stop.wait(POLL_SECONDS)

    def _stable_files(self) -> list[Path]:
        """Files whose size did not change since the previous poll (copy finished)."""
        ready = []
        seen = {}
        for f in sorted(paths.INBOX_DIR.iterdir()):
            if not f.is_file() or f.suffix.lower() not in ALLOWED_EXT:
                continue
            size = f.stat().st_size
            seen[str(f)] = size
            if self._sizes.get(str(f)) == size and size > 0:
                ready.append(f)
        self._sizes = seen
        return ready

    def _process(self, f: Path) -> None:
        """Scan one dropped file, then move it out of the inbox (never delete)."""
        self.on_event(f"Inbox: scanning {f.name}...")
        src = str(f)
        try:
            # on_page_done streams each finished page so multi-page PDFs show up
            # (and auto-boost) page by page instead of after the whole file.
            # skip_pages resumes a partially-done PDF (restart / re-drop) instead of
            # re-scanning page 1 and duplicating its finished pages — the real
            # duplicate bug the audit (P1) flagged. A re-dropped IMAGE is
            # deliberately re-scanned: the unattended door can't prompt like the
            # GUI's _already_scanned, doing nothing would look broken, and a
            # single-image redo self-heals via fail_orphans + _clear_failed_attempts.
            results = scan_service.run_source(
                src, self.settings,
                on_progress=lambda m: self.on_event(f"Inbox {f.name}: {m}"),
                on_page_done=self.on_job_done,
                skip_pages=store.done_pages(src))  # empty for images / fresh PDFs
        except Exception as exc:
            self._move(f, paths.INBOX_FAILED)
            self.on_event(f"Inbox: ❌ {f.name} failed — {exc}")
            return
        self._move(f, paths.INBOX_PROCESSED)
        if not results:  # 0-page / unreadable PDF — produced nothing, but is NOT a failure
            self.on_event(f"Inbox: {f.name} produced no pages (empty or unreadable) — skipped.")
            return
        jobs = ", ".join(str(r.job_id) for r in results)
        self.on_event(f"Inbox: ✅ {f.name} → job(s) {jobs} "
                      f"(confidence {results[-1].mean_conf}%)")

    def _move(self, f: Path, target_dir: Path) -> None:
        """Move into processed/failed, adding a numeric suffix on name clashes."""
        self._sizes.pop(str(f), None)
        target = target_dir / f.name
        n = 1
        while target.exists():
            target = target_dir / f"{f.stem}_{n}{f.suffix}"
            n += 1
        shutil.move(str(f), str(target))
