"""Root window — tabbed shell wiring features together (no business logic here)."""
import customtkinter as ctk

from src.core.config import paths
from src.core.config import settings as settings_mod
from src.core.services import introduce
from src.features.api.service import ApiServer
from src.features.boost.controller import BoostController
from src.features.scan.controller import ScanController
from src.features.scan.view import ScanView
from src.features.jobs.view import JobsView
from src.features.settings.view import SettingsView
from src.features.tray.service import TrayIcon
from src.features.updater.service import AutoUpdater
from src.features.watcher.service import InboxWatcher

APP_NAME = "OCR Agentic AI"
APP_VERSION = "v0.1.1"  # carry rule: 0.0.9 + 1 rolls the middle place


class App(ctk.CTk):
    """Main application window: Scan / Jobs / Settings tabs."""

    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        self.title(f"{APP_NAME} {APP_VERSION} — the eyes of Open-Claw")
        self.geometry("900x620")
        self.minsize(720, 480)
        icon = paths.asset("icon.ico")
        if icon.exists():
            self.iconbitmap(default=str(icon))  # title bar + taskbar identity (branding #3)

        paths.ensure_dirs()
        self.settings = settings_mod.load()
        self.settings.save()  # materialize defaults so Nick can inspect/edit the JSON
        introduce.write_introduction(self.settings, APP_VERSION)  # handshake file for the Heart
        self.boost = BoostController(self.settings)

        tabs = ctk.CTkTabview(self)
        tabs.pack(fill="both", expand=True, padx=8, pady=8)
        scan_tab = tabs.add("Scan")
        jobs_tab = tabs.add("Jobs")
        settings_tab = tabs.add("Settings")

        self.scan_view = ScanView(scan_tab, ScanController(self.settings),
                                  on_job_done=self._after_scan)
        self.scan_view.pack(fill="both", expand=True)
        self.jobs_view = JobsView(jobs_tab)
        self.jobs_view.pack(fill="both", expand=True)
        self.settings_view = SettingsView(settings_tab, self.settings, self.boost)
        self.settings_view.pack(fill="both", expand=True)

        # Background interfaces for Open-Claw — same engine, two doors.
        self.watcher = InboxWatcher(
            self.settings,
            on_event=lambda msg: self.after(0, self.scan_view._set_status, msg),
            on_job_done=lambda res: self.after(0, self._after_scan, res))
        if self.settings.watch_inbox:
            self.watcher.start()
        self.api = ApiServer(self.settings, APP_VERSION,
                             on_event=lambda msg: self.after(0, self.scan_view._set_status, msg))
        if self.settings.api_enabled:
            err = self.api.start()
            if err:
                self.after(0, self.scan_view._set_status, f"⚠ {err}")

        # Tray: closing the window hides the app; background doors stay open.
        # Tray callbacks come from pystray's thread → marshal onto Tk with after().
        self.tray = TrayIcon(APP_NAME,
                             on_open=lambda: self.after(0, self._show_window),
                             on_quit=lambda: self.after(0, self._quit))
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # Silent auto-update (GitHub Releases) — staged in background, installs on quit.
        self.updater = AutoUpdater(
            self.settings, APP_VERSION,
            on_event=lambda msg: self.after(0, self.scan_view._set_status, msg))
        self.updater.check_async()

    def _on_close(self) -> None:
        """Window X button: hide to tray when enabled, otherwise quit for real."""
        if self.settings.tray_enabled:
            self.tray.start()
            self.withdraw()
        else:
            self._quit()

    def _show_window(self) -> None:
        self.deiconify()
        self.lift()
        self.focus_force()

    def _quit(self) -> None:
        """Full shutdown: stop the background doors, drop the tray icon, exit.
        A staged update fires its silent installer the moment we're gone."""
        self.watcher.stop()
        self.api.stop()
        self.tray.stop()
        self.updater.apply_on_exit()
        self.destroy()

    def _after_scan(self, _result) -> None:
        """Per finished Job (each PDF page streams here): refresh the Jobs list
        and auto-drain the Boost Queue when AI Boost is enabled."""
        self.settings_view.refresh_queue()
        self.jobs_view.refresh()
        self.boost.auto_send(
            on_progress=lambda msg: self.after(0, self.scan_view._set_status, msg),
            on_done=lambda s: self.after(0, self._boost_done, s),
        )

    def _boost_done(self, summary) -> None:
        self.scan_view._set_status(
            f"✅ AI Boost: answered {summary.answered}, failed {summary.failed}."
            + (f" {summary.stopped_reason}" if summary.stopped_reason else ""))
        self.settings_view.refresh_queue()


def run() -> None:
    """Launch the GUI."""
    App().mainloop()
