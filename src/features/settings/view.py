"""Settings tab UI — Gemini key (.env), AI Boost toggle, model, daily cap, boost-now. UI only."""
from tkinter import messagebox

import customtkinter as ctk

from src.core.config.settings import Settings
from src.core.services import gemini
from src.features.boost.controller import BoostController
from src.features.boost.service import FREE_MODEL
from src.features.jobs import service as jobs_service

# The main Gemini models (display name → API model id). Free tier is locked to
# FREE_MODEL; the rest need the paid-tier unlock below.
MODELS = {
    "Gemini 3.1 Flash Lite (free tier)": "gemini-3.1-flash-lite",
    "Gemini 3.1 Pro": "gemini-3.1-pro",
    "Gemini 3.5 Flash": "gemini-3.5-flash",
    "Gemini 2.5 Pro": "gemini-2.5-pro",
    "Gemini 2.5 Flash": "gemini-2.5-flash",
    "Gemini 2.5 Flash Lite": "gemini-2.5-flash-lite",
    "Gemini 2 Flash": "gemini-2.0-flash",
    "Gemini 2 Flash Lite": "gemini-2.0-flash-lite",
}

PAID_CONSENT = (
    "Unlock paid tier?\n\n"
    "This removes the free-tier safety limits:\n"
    "  • rate throttle 14 requests/min → 0.5 s pacing\n"
    "  • daily request cap → ignored\n"
    "  • all Gemini models selectable\n\n"
    "Your API key will be billed by Google for every request.\n"
    "A FREE key used here will just hit quota errors (429).\n\n"
    "I understand and accept the costs."
)


class SettingsView(ctk.CTkFrame):
    """The Settings tab: AI Boost configuration + manual queue drain."""

    def __init__(self, master, settings: Settings, boost: BoostController):
        super().__init__(master, fg_color="transparent")
        self.settings = settings
        self.boost = boost

        box = ctk.CTkFrame(self)
        box.pack(fill="x", padx=16, pady=(16, 8))
        ctk.CTkLabel(box, text="🤖 AI Boost (Gemini)",
                     font=ctk.CTkFont(weight="bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=12, pady=(10, 6))

        self.enabled_var = ctk.BooleanVar(value=settings.ai_boost_enabled)
        ctk.CTkSwitch(box, text="Enable AI Boost (send unclear sections to Gemini when online)",
                      variable=self.enabled_var).grid(
            row=1, column=0, columnspan=2, sticky="w", padx=12, pady=4)

        ctk.CTkLabel(box, text="Gemini API key (AI Studio)").grid(
            row=2, column=0, sticky="w", padx=12, pady=4)
        self.key_entry = ctk.CTkEntry(box, show="•", width=360,
                                      placeholder_text="paste key — stored in .env, never in code")
        self.key_entry.grid(row=2, column=1, sticky="we", padx=12, pady=4)
        if gemini.read_api_key():
            self.key_entry.insert(0, gemini.read_api_key())

        self.paid_var = ctk.BooleanVar(value=settings.paid_tier)
        ctk.CTkSwitch(box, text="🔓 Unlock paid tier (no throttle, no daily cap, all models — billed key)",
                      variable=self.paid_var, command=self._toggle_paid).grid(
            row=3, column=0, columnspan=2, sticky="w", padx=12, pady=4)

        ctk.CTkLabel(box, text="Model").grid(row=4, column=0, sticky="w", padx=12, pady=4)
        self.model_menu = ctk.CTkOptionMenu(box, width=360, values=list(MODELS))
        self.model_menu.grid(row=4, column=1, sticky="w", padx=12, pady=4)
        self.model_menu.set(self._display_for(settings.gemini_model))

        ctk.CTkLabel(box, text="Daily request cap (free tier RPD 500; ignored when unlocked)").grid(
            row=5, column=0, sticky="w", padx=12, pady=4)
        self.cap_entry = ctk.CTkEntry(box, width=120)
        self.cap_entry.grid(row=5, column=1, sticky="w", padx=12, pady=4)
        self.cap_entry.insert(0, str(settings.boost_daily_cap))

        ctk.CTkButton(box, text="💾 Save settings", command=self._save).grid(
            row=6, column=0, sticky="w", padx=12, pady=(8, 12))
        self.save_status = ctk.CTkLabel(box, text="", anchor="w")
        self.save_status.grid(row=6, column=1, sticky="w", padx=12, pady=(8, 12))
        box.columnconfigure(1, weight=1)
        self._apply_paid_state()

        iface_box = ctk.CTkFrame(self)
        iface_box.pack(fill="x", padx=16, pady=8)
        ctk.CTkLabel(iface_box, text="🔌 Open-Claw interfaces (apply on next app start)",
                     font=ctk.CTkFont(weight="bold")).grid(
            row=0, column=0, columnspan=3, sticky="w", padx=12, pady=(10, 6))
        self.watch_var = ctk.BooleanVar(value=settings.watch_inbox)
        ctk.CTkSwitch(iface_box, text="Watch data\\inbox (auto-scan dropped files)",
                      variable=self.watch_var).grid(
            row=1, column=0, columnspan=3, sticky="w", padx=12, pady=4)
        self.api_var = ctk.BooleanVar(value=settings.api_enabled)
        ctk.CTkSwitch(iface_box, text="Local API on 127.0.0.1, port:",
                      variable=self.api_var).grid(
            row=2, column=0, sticky="w", padx=12, pady=(4, 12))
        self.port_entry = ctk.CTkEntry(iface_box, width=90)
        self.port_entry.grid(row=2, column=1, sticky="w", padx=(0, 12), pady=4)
        self.port_entry.insert(0, str(settings.api_port))
        self.tray_var = ctk.BooleanVar(value=settings.tray_enabled)
        ctk.CTkSwitch(iface_box, text="Close window → keep running in tray (watcher + API stay up)",
                      variable=self.tray_var).grid(
            row=3, column=0, columnspan=3, sticky="w", padx=12, pady=(4, 12))

        update_box = ctk.CTkFrame(self)
        update_box.pack(fill="x", padx=16, pady=8)
        ctk.CTkLabel(update_box, text="🔄 Updates",
                     font=ctk.CTkFont(weight="bold")).grid(
            row=0, column=0, columnspan=3, sticky="w", padx=12, pady=(10, 6))
        self.auto_update_var = ctk.BooleanVar(value=settings.auto_update)
        ctk.CTkSwitch(update_box, text="Auto-update (checks daily, installs silently on quit)",
                      variable=self.auto_update_var).grid(
            row=1, column=0, columnspan=3, sticky="w", padx=12, pady=4)
        ctk.CTkLabel(update_box, text="GitHub repo (owner/repo)").grid(
            row=2, column=0, sticky="w", padx=12, pady=(4, 12))
        self.repo_entry = ctk.CTkEntry(update_box, width=280,
                                       placeholder_text="empty = updater off")
        self.repo_entry.grid(row=2, column=1, sticky="w", padx=(0, 12), pady=(4, 12))
        if settings.update_repo:
            self.repo_entry.insert(0, settings.update_repo)

        queue_box = ctk.CTkFrame(self)
        queue_box.pack(fill="x", padx=16, pady=8)
        ctk.CTkLabel(queue_box, text="📤 Boost Queue",
                     font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=12, pady=(10, 4))
        self.queue_label = ctk.CTkLabel(queue_box, text="", anchor="w")
        self.queue_label.pack(fill="x", padx=12)
        self.send_btn = ctk.CTkButton(queue_box, text="🚀 Send Boost Queue now",
                                      command=self._send_now)
        self.send_btn.pack(anchor="w", padx=12, pady=(6, 4))
        self.run_status = ctk.CTkLabel(queue_box, text="", anchor="w", wraplength=760,
                                       justify="left")
        self.run_status.pack(fill="x", padx=12, pady=(0, 12))
        self.refresh_queue()

    def refresh_queue(self) -> None:
        """Update the pending count label (called on tab build and after runs)."""
        self.queue_label.configure(
            text=f"{jobs_service.boost_pending()} section(s) waiting for AI Boost")

    @staticmethod
    def _display_for(model_id: str) -> str:
        """Map a stored model id back to its dropdown label (free model on miss)."""
        for display, mid in MODELS.items():
            if mid == model_id:
                return display
        return next(d for d, m in MODELS.items() if m == FREE_MODEL)

    def _toggle_paid(self) -> None:
        """Unlocking requires explicit consent; declining flips the switch back."""
        if self.paid_var.get() and not messagebox.askyesno(
                "Paid tier", PAID_CONSENT, icon="warning", parent=self):
            self.paid_var.set(False)
        self._apply_paid_state()

    def _apply_paid_state(self) -> None:
        """Free tier = model locked to the free one; unlocked = full dropdown."""
        if self.paid_var.get():
            self.model_menu.configure(state="normal")
        else:
            self.model_menu.set(self._display_for(FREE_MODEL))
            self.model_menu.configure(state="disabled")

    def _save(self) -> None:
        """Persist settings.json + .env from the form."""
        key = self.key_entry.get().strip()
        if key:
            gemini.save_api_key(key)
        self.settings.ai_boost_enabled = self.enabled_var.get()
        self.settings.paid_tier = self.paid_var.get()
        self.settings.gemini_model = (MODELS.get(self.model_menu.get(), FREE_MODEL)
                                      if self.settings.paid_tier else FREE_MODEL)
        try:
            self.settings.boost_daily_cap = max(1, int(self.cap_entry.get()))
        except ValueError:
            pass  # keep the previous cap on bad input
        self.settings.watch_inbox = self.watch_var.get()
        self.settings.api_enabled = self.api_var.get()
        self.settings.tray_enabled = self.tray_var.get()
        self.settings.auto_update = self.auto_update_var.get()
        self.settings.update_repo = self.repo_entry.get().strip()
        try:
            self.settings.api_port = int(self.port_entry.get())
        except ValueError:
            pass
        self.settings.save()
        self.save_status.configure(text="✅ Saved.")

    def _send_now(self) -> None:
        """Manually drain the Boost Queue."""
        self.send_btn.configure(state="disabled")
        self.run_status.configure(text="Starting...")
        self.boost.send_pending(
            on_progress=lambda msg: self.after(0, self.run_status.configure, {"text": msg}),
            on_done=lambda s: self.after(0, self._show_summary, s),
            on_error=lambda msg: self.after(0, self._show_error, msg),
        )

    def _show_summary(self, s) -> None:
        text = f"✅ Boost run finished — answered {s.answered}, failed {s.failed}."
        if s.stopped_reason:
            text += f" {s.stopped_reason}"
        self.run_status.configure(text=text)
        self.send_btn.configure(state="normal")
        self.refresh_queue()

    def _show_error(self, msg: str) -> None:
        self.run_status.configure(text=f"❌ {msg}")
        self.send_btn.configure(state="normal")
        self.refresh_queue()
