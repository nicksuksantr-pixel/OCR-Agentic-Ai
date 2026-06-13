"""Scan controller — runs the pipeline on a worker thread and feeds the view callbacks."""
import threading
import time

from src.core.config.settings import Settings
from src.core.services import engine
from src.features.scan import service


class ScanController:
    """Bridges the Scan view and the pipeline; keeps the UI thread free.

    While a scan runs, `progress` holds a dict the Dashboard reads:
    {source, page, pages, section, sections, started}. page/pages stream in per
    finished page; section/sections advance WITHIN a page from the live event
    feed, so the Dashboard bar moves smoothly instead of sitting on "starting..."
    for the whole multi-minute page (v0.2.2).
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self.busy = False
        self.control: service.ScanControl | None = None
        self.progress: dict | None = None

    def engine_ready(self) -> str | None:
        """Configure the local engine; return an error message or None when ready."""
        return engine.configure(self.settings)

    def scan_file(self, path: str, on_progress, on_done, on_error,
                  on_page_done=None, skip_pages: set[int] | None = None,
                  on_event=None) -> None:
        """Start one Source in the background; on_page_done streams each finished
        Job (PDF page) as it completes, on_done receives the full list at the end.
        on_event streams the live page-image + per-section feed to the Scan view.
        skip_pages resumes an interrupted PDF batch."""
        if self.busy:
            on_error("A scan is already running.")
            return
        self.busy = True
        self.control = service.ScanControl()
        self.progress = {"source": path, "page": 0, "pages": None,
                         "section": 0, "sections": 0, "started": time.time()}

        def page_done(result):
            if self.progress is not None:
                self.progress["page"] = result.page or 1
                self.progress["pages"] = result.pages or 1
                # page fully read → its sections count as complete (bar = page/pages)
                self.progress["section"] = self.progress.get("sections", 0)
            if on_page_done:
                on_page_done(result)

        def relay_event(e):
            # Keep the shared progress dict (Dashboard) in step with the live feed,
            # then forward the raw event to the Scan view for its preview.
            p = self.progress
            if p is not None:
                if e.get("page"):
                    p["page"] = e["page"]
                if e.get("pages"):
                    p["pages"] = e["pages"]
                kind = e.get("kind")
                if kind == "page_ready":
                    p["sections"], p["section"] = e.get("sections", 0), 0
                elif kind == "section":
                    p["sections"] = e.get("sections", p["sections"])
                    p["section"] = e.get("idx", 0) + 1
            if on_event:
                on_event(e)

        def work():
            try:
                results = service.run_source(path, self.settings, on_progress,
                                             on_page_done=page_done,
                                             control=self.control,
                                             skip_pages=skip_pages,
                                             on_event=relay_event)
                on_done(results)
            except Exception as exc:
                on_error(str(exc))
            finally:
                self.busy = False
                self.progress = None

        threading.Thread(target=work, daemon=True).start()

    # --- pause / cancel (no-ops when nothing is running) ---

    def pause(self) -> None:
        if self.busy and self.control:
            self.control.pause()

    def resume(self) -> None:
        if self.busy and self.control:
            self.control.resume()

    def cancel(self) -> None:
        if self.busy and self.control:
            self.control.cancel()

    @property
    def paused(self) -> bool:
        return bool(self.busy and self.control and self.control.paused)

    def paused_seconds(self) -> float:
        """Seconds the current scan has spent paused — for an honest ETA (v0.2.2)."""
        return self.control.paused_seconds() if self.control else 0.0
