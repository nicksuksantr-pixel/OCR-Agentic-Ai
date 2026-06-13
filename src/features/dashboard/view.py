"""Dashboard tab — library stats, current batch progress, AI Boost budget, inbox
health, and the shared Activity log (the live feed every background door writes
to). UI only; numbers come from the store, the boost service and the scan
controller. The Activity log is fed by App.log (v0.2.0)."""
import time

import customtkinter as ctk

from src.core.config import paths
from src.core.config.settings import Settings
from src.features.boost import service as boost_service
from src.core.services import store
from src.features.scan.controller import ScanController
from src.shared.ui import theme
from src.shared.ui.widgets import ActivityLog

REFRESH_MS = 2000  # auto-refresh cadence


class DashboardView(ctk.CTkFrame):
    """The Dashboard tab: live stat cards + a scrolling activity feed."""

    def __init__(self, master, settings: Settings, scan_controller: ScanController):
        super().__init__(master, fg_color="transparent")
        self.settings = settings
        self.scan_controller = scan_controller

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # --- current activity card (scan progress) ---
        act = ctk.CTkFrame(self, fg_color=theme.CARD, corner_radius=10)
        act.grid(row=0, column=0, sticky="we", padx=theme.L, pady=(theme.L, theme.S))
        ctk.CTkLabel(act, text="🔄 Current activity", font=theme.font_h2(),
                     anchor="w").pack(fill="x", padx=theme.M, pady=(theme.S, 0))
        self.activity_label = ctk.CTkLabel(act, text="...", anchor="w", justify="left")
        self.activity_label.pack(fill="x", padx=theme.M, pady=(0, theme.XS))
        self.progress_bar = ctk.CTkProgressBar(act)
        self.progress_bar.pack(fill="x", padx=theme.M, pady=(0, theme.M))
        self.progress_bar.set(0)

        # --- two stat cards side by side ---
        cards = ctk.CTkFrame(self, fg_color="transparent")
        cards.grid(row=1, column=0, sticky="we", padx=theme.L, pady=0)
        cards.grid_columnconfigure((0, 1), weight=1)
        self.stats_label = self._card(cards, "📈 Library", 0)
        self.boost_label = self._card(cards, "🤖 AI Boost budget", 1)

        # --- activity log (the live feed) ---
        self.activity_log = ActivityLog(self, title="📜 Activity log")
        self.activity_log.grid(row=2, column=0, sticky="nsew", padx=theme.L, pady=theme.S)

        self.store_label = ctk.CTkLabel(self, text=f"Shared Store: {paths.DATA_DIR}",
                                        anchor="w", text_color=theme.MUTED,
                                        font=theme.font_caption())
        self.store_label.grid(row=3, column=0, sticky="we", padx=theme.L, pady=(0, theme.S))

        self._tick()

    def _card(self, parent, title: str, col: int) -> ctk.CTkLabel:
        frame = ctk.CTkFrame(parent, fg_color=theme.CARD, corner_radius=10)
        frame.grid(row=0, column=col, sticky="nsew", padx=(0 if col == 0 else theme.S, 0),
                   pady=theme.S)
        ctk.CTkLabel(frame, text=title, font=theme.font_h2(), anchor="w").pack(
            fill="x", padx=theme.M, pady=(theme.S, 0))
        label = ctk.CTkLabel(frame, text="...", anchor="w", justify="left")
        label.pack(fill="x", padx=theme.M, pady=(0, theme.M))
        return label

    def _tick(self) -> None:
        """Refresh all numbers; reschedules itself while the widget lives."""
        if not self.winfo_exists():
            return
        try:
            s = store.stats()  # one DB read per tick, shared by both stat cards
            self._update_activity()
            self._update_stats(s)
            self._update_boost(s)
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
        pages = p.get("pages") or 0
        page = p.get("page") or 0
        sections = p.get("sections") or 0
        section = p.get("section") or 0
        state = "⏸ PAUSED" if self.scan_controller.paused else "scanning"
        if pages and sections:
            # Smooth fraction across the whole batch: whole finished pages plus the
            # fraction of the current page's sections that are done (v0.2.2).
            frac = min(max(((page - 1) + section / sections) / pages, 0.0), 1.0)
            self.activity_label.configure(
                text=f"{name} — {state}: page {page}/{pages}, "
                     f"section {section}/{sections}{self._eta(p, frac)}")
            self.progress_bar.set(frac)
        elif pages:
            # Page known but its grid isn't measured yet — show page-level progress.
            self.activity_label.configure(text=f"{name} — {state}: page {page}/{pages}...")
            self.progress_bar.set(max(page - 1, 0) / pages)
        else:
            self.activity_label.configure(text=f"{name} — starting...")
            self.progress_bar.set(0)

    def _eta(self, p: dict, frac: float) -> str:
        """Time-left estimate from elapsed (minus any paused time) and the smooth
        fraction done — paused time is excluded so the ETA does not balloon while
        a scan sits paused (v0.2.2)."""
        if frac <= 0.02:
            return ""
        elapsed = time.time() - p["started"] - self.scan_controller.paused_seconds()
        remaining = max(elapsed, 0.1) / frac * (1 - frac)
        return f" · ~{int(remaining // 60)} min {int(remaining % 60)} s left"

    def _update_stats(self, s: dict) -> None:
        avg = f'{s["avg_conf"]}%' if s["avg_conf"] is not None else "—"
        processed = self._count(paths.INBOX_PROCESSED)
        failed = self._count(paths.INBOX_FAILED)
        inbox = (f'\nInbox: {processed} processed'
                 + (f' · ⚠ {failed} failed' if failed else ' · 0 failed'))
        self.stats_label.configure(
            text=f'{s["total"]} total · ✅ {s["done"]} done · '
                 f'⏳ {s["processing"]} processing · ❌ {s["error"]} error\n'
                 f'Average confidence (done): {avg}{inbox}')

    def _update_boost(self, s: dict) -> None:
        used = boost_service.used_today()
        if self.settings.paid_tier:
            budget = f"requests today: {used} (paid tier — no cap)"
        else:
            budget = f"requests today: {used}/{self.settings.boost_daily_cap} (free tier)"
        self.boost_label.configure(
            text=f"{budget}\nqueue: {s['boost_pending']} pending · "
                 f"{s['boost_answered']} answered all-time\nmodel: {self.settings.gemini_model}")

    @staticmethod
    def _count(folder) -> int:
        try:
            return sum(1 for f in folder.iterdir() if f.is_file())
        except OSError:
            return 0
