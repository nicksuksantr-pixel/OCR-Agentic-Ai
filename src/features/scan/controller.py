"""Scan controller — runs the pipeline on a worker thread and feeds the view callbacks."""
import threading
import time

from src.core.config.settings import Settings
from src.core.services import engine
from src.features.scan import service


class ScanController:
    """Bridges the Scan view and the pipeline; keeps the UI thread free.

    While a scan runs, `progress` holds a dict the Dashboard reads:
    {source, done, pages, started} — done/pages update as pages stream in.
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
                  on_page_done=None, skip_pages: set[int] | None = None) -> None:
        """Start one Source in the background; on_page_done streams each finished
        Job (PDF page) as it completes, on_done receives the full list at the end.
        skip_pages resumes an interrupted PDF batch."""
        if self.busy:
            on_error("A scan is already running.")
            return
        self.busy = True
        self.control = service.ScanControl()
        self.progress = {"source": path, "done": 0, "pages": None,
                         "started": time.time()}

        def page_done(result):
            if self.progress is not None:
                self.progress["done"] = result.page or 1
                self.progress["pages"] = result.pages or 1
            if on_page_done:
                on_page_done(result)

        def work():
            try:
                results = service.run_source(path, self.settings, on_progress,
                                             on_page_done=page_done,
                                             control=self.control,
                                             skip_pages=skip_pages)
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
