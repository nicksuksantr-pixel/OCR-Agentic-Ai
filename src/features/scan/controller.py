"""Scan controller — runs the pipeline on a worker thread and feeds the view callbacks."""
import threading

from src.core.config.settings import Settings
from src.core.services import engine
from src.features.scan import service


class ScanController:
    """Bridges the Scan view and the pipeline; keeps the UI thread free."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.busy = False

    def engine_ready(self) -> str | None:
        """Configure the local engine; return an error message or None when ready."""
        return engine.configure(self.settings)

    def scan_file(self, path: str, on_progress, on_done, on_error,
                  on_page_done=None) -> None:
        """Start one Source in the background; on_page_done streams each finished
        Job (PDF page) as it completes, on_done receives the full list at the end."""
        if self.busy:
            on_error("A scan is already running.")
            return
        self.busy = True

        def work():
            try:
                results = service.run_source(path, self.settings, on_progress,
                                             on_page_done=on_page_done)
                on_done(results)
            except Exception as exc:
                on_error(str(exc))
            finally:
                self.busy = False

        threading.Thread(target=work, daemon=True).start()
