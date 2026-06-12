"""Boost controller — runs the queue drain on a worker thread for the GUI."""
import threading

from src.core.config.settings import Settings
from src.features.boost import service


class BoostController:
    """Bridges Settings/Scan views and the Boost sender; keeps the UI thread free."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.busy = False

    def send_pending(self, on_progress, on_done, on_error) -> None:
        """Drain the Boost Queue in the background; callbacks fire on the worker thread."""
        if self.busy:
            on_error("A boost run is already in progress.")
            return
        if not self.settings.ai_boost_enabled:
            on_error("AI Boost is disabled in Settings.")
            return
        self.busy = True

        def work():
            try:
                on_done(service.send_pending(self.settings, on_progress))
            except Exception as exc:
                on_error(str(exc))
            finally:
                self.busy = False

        threading.Thread(target=work, daemon=True).start()

    def auto_send(self, on_progress, on_done) -> None:
        """Fire-and-forget drain after a scan — silent when disabled or already running."""
        if self.busy or not self.settings.ai_boost_enabled:
            return
        self.send_pending(on_progress, on_done, on_error=lambda msg: None)
