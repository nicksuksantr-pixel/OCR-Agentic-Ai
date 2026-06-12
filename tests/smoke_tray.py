"""Tray smoke — close-to-tray hides the window, Open restores it, Quit shuts down.

Drives the real App through the WM_DELETE_WINDOW path with tray_enabled on/off.
Needs an interactive Windows session (the tray icon joins the real taskbar).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

from src.app.app import App


def check(ok: bool, label: str) -> bool:
    print(("✅" if ok else "❌"), label)
    return ok


def main() -> None:
    app = App()
    app.update()
    app.settings.tray_enabled = True

    app._on_close()  # X button → hide to tray
    app.update()
    all_ok = check(app.state() == "withdrawn", "close hides the window")
    all_ok &= check(app.tray._icon._running, "tray icon thread is running")
    all_ok &= check(app.watcher.running or not app.settings.watch_inbox,
                    "inbox watcher still alive while hidden")
    all_ok &= check(app.api.running or not app.settings.api_enabled,
                    "local API still alive while hidden")

    app._show_window()  # tray menu "Open"
    app.update()
    all_ok &= check(app.state() == "normal", "Open restores the window")

    app._quit()  # tray menu "Quit" → full shutdown
    all_ok &= check(not app.api.running, "API stopped on quit")

    print("\nTRAY SMOKE:", "PASS" if all_ok else "FAIL")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
