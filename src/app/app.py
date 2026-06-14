"""Root window — tabbed shell wiring features together (no business logic here).

v0.2.0: one canonical Shared Store (legacy dev store migrated on first run), and
every background door (scan, inbox watcher, local API, updater, AI Boost) reports
into ONE shared Activity log + a persistent bottom status strip instead of all
overwriting a single Scan-tab label.
"""
import tkinter

import customtkinter as ctk

from src.core.config import paths
from src.core.config import settings as settings_mod
from src.core.services import introduce, store
from src.features.api.service import ApiServer
from src.features.boost.controller import BoostController
from src.features.dashboard.view import DashboardView
from src.features.scan.controller import ScanController
from src.features.scan.view import ScanView
from src.features.jobs.view import JobsView
from src.features.settings.view import SettingsView
from src.features.tray.service import TrayIcon
from src.features.updater.service import AutoUpdater
from src.features.watcher.service import InboxWatcher
from src.shared.ui import theme

APP_NAME = "OCR Agentic AI"
APP_VERSION = "v0.2.6"  # carry rule: each place 0–9, carry at 9
UPDATE_RECHECK_MS = 6 * 60 * 60 * 1000  # re-check every 6 h so a tray-resident app still updates


class App(ctk.CTk):
    """Main application window: Scan / Jobs / Dashboard / Settings tabs."""

    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        self.title(f"{APP_NAME} {APP_VERSION} — the eyes of Open-Claw")
        self.geometry("980x680")
        self.minsize(820, 560)
        icon = paths.asset("icon.ico")
        if icon.exists():
            self.iconbitmap(default=str(icon))  # title bar + taskbar identity (branding #3)

        # One canonical store: migrate the legacy dev folder once, then set up.
        migrate_note = paths.migrate_legacy_store()
        paths.ensure_dirs()
        self.settings = settings_mod.load()
        self.settings.save()  # materialize defaults so Nick can inspect/edit the JSON
        store.set_meta("last_app_version", APP_VERSION)
        introduce.write_introduction(self.settings, APP_VERSION)  # handshake for the Heart
        orphans = store.fail_orphans()
        self.boost = BoostController(self.settings)

        # Persistent one-line status strip at the very bottom — the 'latest event'
        # summary, backed by the scrollable Activity log on the Dashboard. Packed
        # BEFORE the expanding tabview so it always keeps its row.
        strip = ctk.CTkFrame(self, fg_color=theme.CARD, corner_radius=0, height=26)
        strip.pack(fill="x", side="bottom")
        self.status_strip = ctk.CTkLabel(strip, text="Ready.", anchor="w",
                                         text_color=theme.MUTED, font=theme.font_caption())
        self.status_strip.pack(fill="x", padx=theme.M, pady=2)

        # Update bar — slim, prominent, ALWAYS visible when an update is ready,
        # above the tabs. Built now, shown only when the updater says "ready"
        # (Nick: "no status, no button to update, and it never updates itself").
        self.update_bar = ctk.CTkFrame(self, fg_color=theme.ACCENT, corner_radius=0, height=34)
        self.update_label = ctk.CTkLabel(self.update_bar, text="", anchor="w",
                                         text_color="#ffffff", font=theme.font_h2())
        self.update_label.pack(side="left", padx=theme.M, pady=theme.XS)
        ctk.CTkButton(self.update_bar, text="Later", width=64, height=26,
                      fg_color="transparent", hover_color=theme.PRIMARY_HI,
                      command=self._dismiss_update_bar).pack(side="right", padx=(0, theme.M), pady=theme.XS)
        ctk.CTkButton(self.update_bar, text="⬇ Install & restart now", width=180, height=26,
                      fg_color="#ffffff", text_color=theme.ACCENT, hover_color="#e6eefc",
                      command=self._install_update_now).pack(side="right", padx=theme.XS, pady=theme.XS)

        self.tabs = ctk.CTkTabview(self)
        self.tabs.pack(fill="both", expand=True, padx=theme.S, pady=(theme.S, 0))
        scan_tab = self.tabs.add("Scan")
        jobs_tab = self.tabs.add("Jobs")
        dash_tab = self.tabs.add("Dashboard")
        settings_tab = self.tabs.add("Settings")

        self.scan_controller = ScanController(self.settings)
        self.scan_view = ScanView(scan_tab, self.scan_controller, self.settings,
                                  on_job_done=self._after_scan,
                                  on_open_settings=lambda: self.tabs.set("Settings"))
        self.scan_view.pack(fill="both", expand=True)
        self.jobs_view = JobsView(jobs_tab, self.settings)
        self.jobs_view.pack(fill="both", expand=True)
        self.dashboard_view = DashboardView(dash_tab, self.settings, self.scan_controller)
        self.dashboard_view.pack(fill="both", expand=True)
        self.settings_view = SettingsView(settings_tab, self.settings, self.boost,
                                          on_saved=self._on_settings_saved,
                                          on_install_update=self._install_update_now,
                                          app_version=APP_VERSION)
        self.settings_view.pack(fill="both", expand=True)

        # Background interfaces for Open-Claw — same engine, more doors. All of
        # them report into the shared log (with a source tag), never the Scan label.
        self.watcher = InboxWatcher(
            self.settings,
            on_event=lambda msg: self._post(self.log, "WATCH", msg),
            on_job_done=lambda res: self._post(self._after_scan, res))
        if self.settings.watch_inbox:
            self.watcher.start()
        self.api = ApiServer(self.settings, APP_VERSION,
                             on_event=lambda msg: self._post(self.log, "API", msg))
        if self.settings.api_enabled:
            err = self.api.start()
            if err:
                self._post(self.log, "API", err, "warn")

        self.tray = TrayIcon(APP_NAME,
                             on_open=lambda: self._post(self._show_window),
                             on_quit=lambda: self._post(self._quit))
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.updater = AutoUpdater(
            self.settings, APP_VERSION,
            on_event=lambda msg: self._post(self.log, "UPDATE", msg),
            on_ready=lambda tag: self._post(self._update_ready, tag))
        self.settings_view.updater = self.updater
        self.updater.check_async()
        self.after(UPDATE_RECHECK_MS, self._periodic_update_check)

        self.log("APP", f"{APP_NAME} {APP_VERSION} ready.", "ok")
        if migrate_note:
            self.log("APP", migrate_note, "ok")
        if orphans:
            self.log("APP", f"{orphans} interrupted job(s) from the last run marked error "
                     "— re-pick the file to resume (finished pages are skipped).", "warn")

    def _post(self, fn, *args) -> None:
        """Schedule a worker-thread callback on the Tk loop, guarded against a
        window torn down mid-flight (e.g. an update check finishing after quit)."""
        try:
            self.after(0, fn, *args)
        except (RuntimeError, tkinter.TclError):
            pass

    # --- shared activity log --------------------------------------------------

    def log(self, source: str, message: str, level: str = "info") -> None:
        """Single sink for every subsystem's events: bottom strip + Activity log."""
        icon = {"ok": "✅", "warn": "⚠", "error": "❌"}.get(level, "")
        self.status_strip.configure(text=f"{icon} [{source}] {message}".strip())
        if self.dashboard_view.winfo_exists():
            self.dashboard_view.activity_log.append(message, source, level)

    # --- window / lifecycle ---------------------------------------------------

    def _on_close(self) -> None:
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
        self.watcher.stop()
        self.api.stop()
        self.tray.stop()
        self.updater.apply_on_exit()
        self.destroy()

    def _on_settings_saved(self) -> None:
        """After a settings save / engine re-check: refresh the Scan-tab banners."""
        self.scan_view.refresh_banners()
        self.settings_view.refresh_update_status()

    # --- updates --------------------------------------------------------------

    def _update_ready(self, tag: str) -> None:
        """An update was downloaded + verified — show the prominent bar + hint."""
        self.update_label.configure(text=f"🔄 Update {tag} is ready to install.")
        if not self.update_bar.winfo_ismapped():
            self.update_bar.pack(fill="x", side="top", before=self.tabs)
        self.status_strip.configure(
            text=f"✅ [UPDATE] {tag} ready — click 'Install & restart now' (top bar or Settings)")
        self.settings_view.refresh_update_status()

    def _dismiss_update_bar(self) -> None:
        """'Later' — hide the bar; the update stays staged (Settings can still
        install it, and it installs on a real Quit)."""
        self.update_bar.pack_forget()

    def _install_update_now(self) -> None:
        """Install the staged update immediately: stop the doors, hand the setup
        to the detached installer, and let it relaunch us — no manual Quit needed."""
        if not (self.updater.staged_setup and self.updater.staged_setup.exists()):
            self.log("UPDATE", "No update is staged yet — try 'Check now'.", "warn")
            return
        self.log("UPDATE", "Installing update — the app will close and reopen...", "ok")
        self.update_label.configure(text="Installing — the app will restart...")
        self.update_idletasks()
        self._quit()  # apply_on_exit() launches the installer, then it relaunches the app

    def _periodic_update_check(self) -> None:
        """Re-check on a timer so an app left running in the tray still finds updates."""
        if not self.winfo_exists():
            return
        self.updater.check_async()
        self.after(UPDATE_RECHECK_MS, self._periodic_update_check)

    def _after_scan(self, result) -> None:
        """Per finished Job (each PDF page streams here): log the milestone,
        refresh the Jobs list (coalesced) and auto-drain the Boost Queue."""
        page = getattr(result, "page", None)
        where = f"page {page}/{result.pages}" if page else f"job {result.job_id}"
        self.log("SCAN", f"{where} done — confidence {result.mean_conf}%", "ok")
        self.settings_view.refresh_queue()
        self.jobs_view.refresh()
        self.boost.auto_send(
            on_progress=lambda msg: self._post(self.log, "BOOST", msg),
            on_done=lambda s: self._post(self._boost_done, s),
        )

    def _boost_done(self, summary) -> None:
        level = "warn" if summary.stopped_reason and not summary.answered else "ok"
        msg = f"answered {summary.answered}, failed {summary.failed}."
        if summary.stopped_reason:
            msg += f" {summary.stopped_reason}"
        self.log("BOOST", msg, level)
        self.settings_view.refresh_queue()


def run() -> None:
    """Launch the GUI."""
    App().mainloop()
