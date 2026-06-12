"""Dashboard tab UI — library stats, current batch progress, AI Boost budget.
UI only; numbers come from the store, the boost service and the scan controller."""
import time

import customtkinter as ctk

from src.core.config import paths
from src.core.config.settings import Settings
from src.core.services import store
from src.features.boost import service as boost_service
from src.features.scan.controller import ScanController

REFRESH_MS = 2000  # auto-refresh cadence


class DashboardView(ctk.CTkFrame):
    """The Dashboard tab: three live boxes refreshed every couple of seconds."""

    def __init__(self, master, settings: Settings, scan_controller: ScanController):
        super().__init__(master, fg_color="transparent")
        self.settings = settings
        self.scan_controller = scan_controller

        self.activity_label = self._box("🔄 Current activity")
        self.progress_bar = ctk.CTkProgressBar(self.activity_label.master)
        self.progress_bar.pack(fill="x", padx=12, pady=(0, 12))
        self.progress_bar.set(0)

        self.stats_label = self._box("📈 Library")
        self.boost_label = self._box("🤖 AI Boost budget")

        ctk.CTkLabel(self, text=f"Shared Store: {paths.DATA_DIR}",
                     anchor="w", text_color="gray").pack(fill="x", padx=16)

        self._tick()

    def _box(self, title: str) -> ctk.CTkLabel:
        frame = ctk.CTkFrame(self)
        frame.pack(fill="x", padx=16, pady=(16, 0))
        ctk.CTkLabel(frame, text=title, font=ctk.CTkFont(weight="bold"),
                     anchor="w").pack(fill="x", padx=12, pady=(10, 2))
        label = ctk.CTkLabel(frame, text="...", anchor="w", justify="left")
        label.pack(fill="x", padx=12, pady=(0, 12))
        return label

    def _tick(self) -> None:
        """Refresh all numbers; reschedules itself while the widget lives."""
        if not self.winfo_exists():
            return
        try:
            self._update_activity()
            self._update_stats()
            self._update_boost()
        except Exception as exc:  # a hiccup must never kill the refresh loop
            self.activity_label.configure(text=f"⚠ {exc}")
        self.after(REFRESH_MS, self._tick)

    def _update_activity(self) -> None:
        p = self.scan_controller.progress
        if not p:
            self.activity_label.configure(text="Idle — no scan running in this window.")
            self.progress_bar.set(0)
            return
        name = p["source"].replace("\\", "/").rsplit("/", 1)[-1]
        done, pages = p["done"], p["pages"]
        if pages:
            elapsed = time.time() - p["started"]
            eta = ""
            if done:
                remaining = (elapsed / done) * (pages - done)
                eta = f" · ~{int(remaining // 60)} min {int(remaining % 60)} s left"
            state = "⏸ PAUSED" if self.scan_controller.paused else "scanning"
            self.activity_label.configure(
                text=f"{name} — {state}: page {done}/{pages} done{eta}")
            self.progress_bar.set(done / pages)
        else:
            self.activity_label.configure(text=f"{name} — starting...")
            self.progress_bar.set(0)

    def _update_stats(self) -> None:
        s = store.stats()
        avg = f'{s["avg_conf"]}%' if s["avg_conf"] is not None else "—"
        self.stats_label.configure(
            text=f'Jobs: {s["total"]} total · ✅ {s["done"]} done · '
                 f'⏳ {s["processing"]} processing · ❌ {s["error"]} error\n'
                 f'Average confidence (done): {avg}')

    def _update_boost(self) -> None:
        used = boost_service.used_today()
        s = store.stats()
        if self.settings.paid_tier:
            budget = f"requests today: {used} (paid tier unlocked — no cap)"
        else:
            budget = f"requests today: {used}/{self.settings.boost_daily_cap} (free tier)"
        self.boost_label.configure(
            text=f"{budget}\nqueue: {s['boost_pending']} pending · "
                 f"{s['boost_answered']} answered all-time · "
                 f"model: {self.settings.gemini_model}")
