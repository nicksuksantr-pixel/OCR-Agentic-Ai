"""System tray — closing the window hides the app; watcher + API keep running.

CONTEXT app-form requirement: the program keeps serving Open-Claw (inbox watcher,
local API) when the window is closed. pystray runs its own Win32 message loop in
a daemon thread (run_detached); menu callbacks arrive on that thread, so anything
touching Tk is marshalled back with widget.after(0, ...) by the caller.

The tray uses the real app icon (assets/icon.png — branding rule #3) and falls
back to a runtime-drawn eye glyph if the asset is ever missing.
"""
import pystray
from PIL import Image, ImageDraw

from src.core.config import paths


def _eye_image(size: int = 64) -> Image.Image:
    """Draw the placeholder tray glyph: a simple eye on transparent ground."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((4, 16, size - 4, size - 16), fill=(30, 30, 30, 255),
              outline=(200, 200, 200, 255), width=3)
    d.ellipse((size // 2 - 11, size // 2 - 11, size // 2 + 11, size // 2 + 11),
              fill=(0, 160, 255, 255))
    d.ellipse((size // 2 - 4, size // 2 - 4, size // 2 + 4, size // 2 + 4),
              fill=(255, 255, 255, 255))
    return img


class TrayIcon:
    """Owns the pystray icon; App provides the open/quit callbacks."""

    def __init__(self, app_name: str, on_open, on_quit):
        icon_path = paths.asset("icon.png")
        image = Image.open(icon_path) if icon_path.exists() else _eye_image()
        self._running = False  # our own flag — don't depend on pystray internals
        self._icon = pystray.Icon(
            app_name, icon=image, title=f"{app_name} — running",
            menu=pystray.Menu(
                pystray.MenuItem("Open", lambda: on_open(), default=True),
                pystray.MenuItem("Quit", lambda: on_quit()),
            ))

    @property
    def visible(self) -> bool:
        return self._running

    def start(self) -> None:
        """Show the tray icon (own message-loop thread; no-op if already up).
        Wrapped so a tray failure can never block the window's close handler."""
        if self._running:
            return
        try:
            self._icon.run_detached()
            self._running = True
        except Exception:
            self._running = False  # tray unavailable — caller still hides/quits fine

    def stop(self) -> None:
        if not self._running:
            return
        try:
            self._icon.stop()
        except Exception:
            pass
        finally:
            self._running = False
