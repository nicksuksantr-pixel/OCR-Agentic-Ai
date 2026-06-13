"""Jobs controller — runs every heavy Jobs-tab operation on a worker thread.

The Jobs tab used to call the service straight from click callbacks on the Tk
main thread: rebuilding the whole list (a DB query + a widget per job), decoding
preview images, and rendering the full-image overlay all blocked the event loop,
so the window greyed out / "wouldn't refresh" (Nick's "tabs hang"). This mirrors
ScanController/BoostController: the view hands work here, it runs off-thread, and
the result is marshalled back with the view's own after(0, ...).
"""
import threading

from src.core.config.settings import Settings


class JobsController:
    """Bridges the Jobs view and the (DB + file + image) service off the UI thread."""

    def __init__(self, settings: Settings):
        self.settings = settings

    def run(self, fn, on_done, on_error=None) -> None:
        """Run fn() in the background, then call on_done(result). on_done/on_error
        fire on the WORKER thread — the view wraps them in self.after(0, ...) to
        touch widgets safely."""
        def work():
            try:
                result = fn()
            except Exception as exc:  # surfaced, never swallowed silently
                if on_error:
                    on_error(exc)
                return
            on_done(result)

        threading.Thread(target=work, daemon=True).start()
