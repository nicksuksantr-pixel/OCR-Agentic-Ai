"""Settings tab UI — Gemini key (.env), AI Boost, OCR engine, interfaces,
updates, boost queue. UI only.

v0.2.0: the whole tab scrolls (so the lower sections survive a small window), the
Tesseract path is finally editable with a Browse + Re-check so a missing engine
isn't a dead end, and bad numeric input is reported instead of silently kept
behind a misleading '✅ Saved.'.
"""
from tkinter import filedialog

import customtkinter as ctk

from src.core.config.settings import Settings
from src.core.services import engine, gemini
from src.features.boost.controller import BoostController
from src.features.boost.service import FREE_MODEL
from src.features.jobs import service as jobs_service
from src.shared.ui import theme, widgets

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

# OCR language combos → the Tesseract lang join-string stored in Settings.languages.
# A fixed 3-item list (not a free-form multiselect) covers the documented language
# policy and keeps the change small; the picker only ever writes one of these.
LANGS = {
    "Thai + English": "tha+eng",
    "English only": "eng",
    "Thai only": "tha",
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
    """The Settings tab: AI Boost + OCR engine + interfaces + updates + queue."""

    def __init__(self, master, settings: Settings, boost: BoostController,
                 on_saved=None, on_install_update=None, app_version=""):
        super().__init__(master, fg_color="transparent")
        self.settings = settings
        self.boost = boost
        self.on_saved = on_saved                 # App hook — refresh Scan-tab banners after a save
        self.on_install_update = on_install_update  # App hook — install the staged update now
        self.app_version = app_version
        self.updater = None                      # attached by the App after construction

        body = ctk.CTkScrollableFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True)

        self._build_boost(body)
        self._build_ocr(body)
        self._build_interfaces(body)
        self._build_updates(body)
        self._build_queue(body)
        self._apply_paid_state()
        self.refresh_queue()
        self._update_status_tick()

    # --- sections -------------------------------------------------------------

    @staticmethod
    def _section(parent, title: str) -> ctk.CTkFrame:
        box = ctk.CTkFrame(parent, fg_color=theme.CARD, corner_radius=10)
        box.pack(fill="x", padx=theme.S, pady=theme.S)
        ctk.CTkLabel(box, text=title, font=theme.font_h2()).pack(
            anchor="w", padx=theme.M, pady=(theme.M, theme.XS))
        return box

    def _build_boost(self, parent) -> None:
        box = self._section(parent, "🤖 AI Boost (Gemini)")
        grid = ctk.CTkFrame(box, fg_color="transparent")
        grid.pack(fill="x", padx=theme.M, pady=(0, theme.M))
        grid.columnconfigure(1, weight=1)

        self.enabled_var = ctk.BooleanVar(value=self.settings.ai_boost_enabled)
        ctk.CTkSwitch(grid, text="Enable AI Boost (send unclear sections to Gemini when online)",
                      variable=self.enabled_var).grid(row=0, column=0, columnspan=2,
                                                      sticky="w", pady=theme.XS)
        ctk.CTkLabel(grid, text="Gemini API key (AI Studio)").grid(row=1, column=0, sticky="w", pady=theme.XS)
        self.key_entry = ctk.CTkEntry(grid, show="•",
                                      placeholder_text="paste key — stored in .env, never in code")
        self.key_entry.grid(row=1, column=1, sticky="we", padx=(theme.S, 0), pady=theme.XS)
        existing = gemini.read_api_key()
        if existing:
            self.key_entry.insert(0, existing)
        self.paid_var = ctk.BooleanVar(value=self.settings.paid_tier)
        ctk.CTkSwitch(grid, text="🔓 Unlock paid tier (no throttle/cap, all models — billed key)",
                      variable=self.paid_var, command=self._toggle_paid).grid(
            row=2, column=0, columnspan=2, sticky="w", pady=theme.XS)
        ctk.CTkLabel(grid, text="Model").grid(row=3, column=0, sticky="w", pady=theme.XS)
        self.model_menu = ctk.CTkOptionMenu(grid, values=list(MODELS),
                                            command=self._on_model_change)
        self.model_menu.grid(row=3, column=1, sticky="w", padx=(theme.S, 0), pady=theme.XS)
        self.model_menu.set(self._display_for(self.settings.gemini_model))
        ctk.CTkLabel(grid, text="Daily request cap (free tier; ignored when unlocked)").grid(
            row=4, column=0, sticky="w", pady=theme.XS)
        self.cap_entry = ctk.CTkEntry(grid, width=120)
        self.cap_entry.grid(row=4, column=1, sticky="w", padx=(theme.S, 0), pady=theme.XS)
        self.cap_entry.insert(0, str(self.settings.boost_daily_cap))

        save_row = ctk.CTkFrame(box, fg_color="transparent")
        save_row.pack(fill="x", padx=theme.M, pady=(0, theme.M))
        ctk.CTkButton(save_row, text="💾 Save settings", command=self._save,
                      **theme.primary_btn()).pack(side="left")
        self.save_status = ctk.CTkLabel(save_row, text="", anchor="w")
        self.save_status.pack(side="left", padx=theme.M)

    def _build_ocr(self, parent) -> None:
        box = self._section(parent, "🔠 OCR engine")
        row = ctk.CTkFrame(box, fg_color="transparent")
        row.pack(fill="x", padx=theme.M, pady=(0, theme.XS))
        row.columnconfigure(0, weight=1)
        ctk.CTkLabel(row, text="Tesseract executable path").grid(row=0, column=0, sticky="w")
        self.tess_entry = ctk.CTkEntry(row, placeholder_text=r"C:\Program Files\Tesseract-OCR\tesseract.exe")
        self.tess_entry.grid(row=1, column=0, sticky="we", pady=theme.XS)
        if self.settings.tesseract_path:
            self.tess_entry.insert(0, self.settings.tesseract_path)
        ctk.CTkButton(row, text="Browse...", width=90, command=self._browse_tesseract,
                      **theme.ghost_btn()).grid(row=1, column=1, padx=(theme.S, theme.XS), pady=theme.XS)
        ctk.CTkButton(row, text="🔁 Re-check", width=100, command=self._recheck_engine,
                      **theme.ghost_btn()).grid(row=1, column=2, pady=theme.XS)
        lang_row = ctk.CTkFrame(box, fg_color="transparent")
        lang_row.pack(fill="x", padx=theme.M, pady=(theme.XS, 0))
        ctk.CTkLabel(lang_row, text="OCR languages").pack(side="left")
        self.lang_menu = ctk.CTkOptionMenu(lang_row, values=list(LANGS))
        self.lang_menu.pack(side="left", padx=theme.S)
        self.lang_menu.set(self._display_for_lang(self.settings.languages))
        self.engine_status = ctk.CTkLabel(box, text="", anchor="w", font=theme.font_caption())
        self.engine_status.pack(fill="x", padx=theme.M)
        self.auto_lang_var = ctk.BooleanVar(value=self.settings.auto_language)
        ctk.CTkSwitch(box, text="Auto language detect — drop the Thai pass on English-only "
                               "pages (stops stray Thai glyph noise on drawings)",
                      variable=self.auto_lang_var).pack(anchor="w", padx=theme.M, pady=(theme.XS, theme.M))

    def _build_interfaces(self, parent) -> None:
        box = self._section(parent, "🔌 Open-Claw interfaces (apply on next app start)")
        self.watch_var = ctk.BooleanVar(value=self.settings.watch_inbox)
        ctk.CTkSwitch(box, text="Watch data\\inbox (auto-scan dropped files)",
                      variable=self.watch_var).pack(anchor="w", padx=theme.M, pady=theme.XS)
        api_row = ctk.CTkFrame(box, fg_color="transparent")
        api_row.pack(fill="x", padx=theme.M, pady=theme.XS)
        self.api_var = ctk.BooleanVar(value=self.settings.api_enabled)
        ctk.CTkSwitch(api_row, text="Local API on 127.0.0.1, port:",
                      variable=self.api_var).pack(side="left")
        self.port_entry = ctk.CTkEntry(api_row, width=90)
        self.port_entry.pack(side="left", padx=theme.S)
        self.port_entry.insert(0, str(self.settings.api_port))
        self.tray_var = ctk.BooleanVar(value=self.settings.tray_enabled)
        ctk.CTkSwitch(box, text="Close window → keep running in tray (watcher + API stay up)",
                      variable=self.tray_var).pack(anchor="w", padx=theme.M, pady=(theme.XS, theme.M))

    def _build_updates(self, parent) -> None:
        box = self._section(parent, "🔄 Updates")
        ctk.CTkLabel(box, text=f"Installed version: {self.app_version}",
                     anchor="w").pack(fill="x", padx=theme.M)
        # Live status + the explicit install button (Nick: "no status, no button").
        status_row = ctk.CTkFrame(box, fg_color="transparent")
        status_row.pack(fill="x", padx=theme.M, pady=theme.XS)
        self.update_status = ctk.CTkLabel(status_row, text="—", anchor="w",
                                          text_color=theme.MUTED)
        self.update_status.pack(side="left", fill="x", expand=True)
        self.install_btn = ctk.CTkButton(status_row, text="⬇ Install & restart now", width=170,
                                         state="disabled", command=self._install_now,
                                         **theme.primary_btn())
        self.install_btn.pack(side="right")
        self.auto_update_var = ctk.BooleanVar(value=self.settings.auto_update)
        ctk.CTkSwitch(box, text="Auto-update (checks on start + every few hours; "
                               "shows a bar when a new version is ready)",
                      variable=self.auto_update_var).pack(anchor="w", padx=theme.M, pady=theme.XS)
        row = ctk.CTkFrame(box, fg_color="transparent")
        row.pack(fill="x", padx=theme.M, pady=(theme.XS, theme.M))
        row.columnconfigure(1, weight=1)
        ctk.CTkLabel(row, text="GitHub repo (owner/repo)").grid(row=0, column=0, sticky="w")
        self.repo_entry = ctk.CTkEntry(row, placeholder_text="empty = updater off")
        self.repo_entry.grid(row=0, column=1, sticky="we", padx=theme.S)
        if self.settings.update_repo:
            self.repo_entry.insert(0, self.settings.update_repo)
        ctk.CTkButton(row, text="🔄 Check now", width=110, command=self._check_updates,
                      **theme.ghost_btn()).grid(row=0, column=2)

    _STATE_TEXT = {
        "disabled": ("Updater is off — enable Auto-update below.", theme.MUTED),
        "idle": ("", theme.MUTED),
        "checking": ("🔄 Checking for updates...", theme.MUTED),
        "uptodate": ("✅ You are on the latest version.", theme.SUCCESS),
        "available": ("A newer version is available (run the installer to update).", theme.WARN),
        "downloading": ("⬇ Downloading the update...", theme.MUTED),
        "ready": ("✅ Update ready — click 'Install & restart now'.", theme.SUCCESS),
        "error": ("⚠ Update check failed (offline or repo unreachable).", theme.WARN),
    }

    def refresh_update_status(self) -> None:
        """Reflect the updater's current state in the label + install button."""
        if not hasattr(self, "update_status"):
            return
        state = getattr(self.updater, "state", "idle") if self.updater else "idle"
        text, color = self._STATE_TEXT.get(state, ("", theme.MUTED))
        if state == "downloading" and self.updater and self.updater.latest_tag:
            text = f"⬇ Downloading {self.updater.latest_tag}..."
        if state == "ready" and self.updater and self.updater.staged_tag:
            text = f"✅ Update {self.updater.staged_tag} ready — click 'Install & restart now'."
        self.update_status.configure(text=text or "—", text_color=color)
        self.install_btn.configure(state="normal" if state == "ready" else "disabled")

    def _update_status_tick(self) -> None:
        if not self.winfo_exists():
            return
        self.refresh_update_status()
        self.after(2000, self._update_status_tick)

    def _install_now(self) -> None:
        if self.on_install_update:
            self.on_install_update()

    def _build_queue(self, parent) -> None:
        box = self._section(parent, "📤 Boost Queue")
        self.queue_label = ctk.CTkLabel(box, text="", anchor="w")
        self.queue_label.pack(fill="x", padx=theme.M)
        self.send_btn = ctk.CTkButton(box, text="🚀 Send Boost Queue now",
                                      command=self._send_now, **theme.primary_btn())
        self.send_btn.pack(anchor="w", padx=theme.M, pady=(theme.S, theme.XS))
        self.run_status = ctk.CTkLabel(box, text="", anchor="w", wraplength=760, justify="left")
        self.run_status.pack(fill="x", padx=theme.M, pady=(0, theme.M))

    # --- behaviour ------------------------------------------------------------

    def refresh_queue(self) -> None:
        self.queue_label.configure(
            text=f"{jobs_service.boost_pending()} section(s) waiting for AI Boost")

    @staticmethod
    def _display_for(model_id: str) -> str:
        for display, mid in MODELS.items():
            if mid == model_id:
                return display
        return next(d for d, m in MODELS.items() if m == FREE_MODEL)

    @staticmethod
    def _display_for_lang(lang_string: str) -> str:
        """Menu label for a stored Settings.languages join-string (falls back to
        the tha+eng default for any unrecognised value)."""
        for display, value in LANGS.items():
            if value == lang_string:
                return display
        return next(d for d, v in LANGS.items() if v == "tha+eng")

    def _browse_tesseract(self) -> None:
        path = filedialog.askopenfilename(
            title="Locate tesseract.exe",
            filetypes=[("tesseract.exe", "tesseract.exe"), ("All files", "*.*")], parent=self)
        if path:
            self.tess_entry.delete(0, "end")
            self.tess_entry.insert(0, path)

    def _recheck_engine(self) -> None:
        self.settings.tesseract_path = self.tess_entry.get().strip() or self.settings.tesseract_path
        err = engine.configure(self.settings)
        if err:
            self.engine_status.configure(text=f"❌ {err}", text_color=theme.DANGER_HI)
        else:
            # Engine is found — now check the SELECTED languages are actually
            # installed. Without this, a dev/portable run missing tha.traineddata
            # passes this check and then throws on the first OCR call. Warn here
            # instead (installed .exe bundles tha, so end users never see this).
            selected = LANGS.get(self.lang_menu.get(), self.settings.languages)
            installed = set(engine.available_languages())
            missing = [lang for lang in selected.split("+") if lang not in installed]
            if missing:
                names = ", ".join(f"'{m}'" for m in missing)
                self.engine_status.configure(
                    text=(f"⚠ Language {names} is selected but not installed — scans will "
                          "fail until it is added or you switch to an installed language."),
                    text_color=theme.WARN)
            else:
                self.engine_status.configure(text="✅ Tesseract found and ready.",
                                             text_color=theme.SUCCESS)
        if self.on_saved:
            self.on_saved()  # re-enable the Scan button if the engine is now ready

    def _check_updates(self) -> None:
        if self.updater is None:
            self.update_status.configure(text="Updater not ready yet — try again.",
                                         text_color=theme.MUTED)
            return
        self.updater.check_async(manual=True)
        self.refresh_update_status()

    def _toggle_paid(self) -> None:
        if self.paid_var.get() and not widgets.ask_yesno(
                self, "Paid tier", PAID_CONSENT, kind="warn"):
            self.paid_var.set(False)
        self._apply_paid_state()
        self._persist_tier()

    def _on_model_change(self, _choice=None) -> None:
        """Persist the model pick the moment it changes (CTkOptionMenu passes the
        chosen value). Free tier stays hard-locked to FREE_MODEL."""
        self._persist_tier()

    def _persist_tier(self) -> None:
        """Save paid_tier + gemini_model on change so they survive leaving the
        tab without Save — these are plain settings.json values (no service
        restart), mirroring what _save() writes for the same two fields."""
        self.settings.paid_tier = self.paid_var.get()
        self.settings.gemini_model = (MODELS.get(self.model_menu.get(), FREE_MODEL)
                                      if self.settings.paid_tier else FREE_MODEL)
        self.settings.save()

    def _apply_paid_state(self) -> None:
        if self.paid_var.get():
            self.model_menu.configure(state="normal")
        else:
            self.model_menu.set(self._display_for(FREE_MODEL))
            self.model_menu.configure(state="disabled")

    def _save(self) -> None:
        """Validate, then persist settings.json + .env from the form."""
        # Numeric fields first — reject bad input loudly instead of '✅ Saved.'.
        try:
            cap = max(1, int(self.cap_entry.get()))
        except ValueError:
            self.save_status.configure(text="⚠ Daily cap must be a whole number — not saved.",
                                       text_color=theme.DANGER_HI)
            return
        try:
            port = int(self.port_entry.get())
            if not (1 <= port <= 65535):
                raise ValueError
        except ValueError:
            self.save_status.configure(text="⚠ API port must be 1–65535 — not saved.",
                                       text_color=theme.DANGER_HI)
            return

        # Capture the three interface fields BEFORE reassigning them — they are
        # read once at App init and only take effect on restart (the watcher /
        # API are not rebound live), so the Save toast must say so honestly
        # instead of a bare '✅ Saved.' that implies an immediate effect.
        interfaces_changed = (
            self.settings.watch_inbox != self.watch_var.get()
            or self.settings.api_enabled != self.api_var.get()
            or self.settings.api_port != port)

        key = self.key_entry.get().strip()
        if key:
            gemini.save_api_key(key)
        self.settings.ai_boost_enabled = self.enabled_var.get()
        self.settings.paid_tier = self.paid_var.get()
        self.settings.gemini_model = (MODELS.get(self.model_menu.get(), FREE_MODEL)
                                      if self.settings.paid_tier else FREE_MODEL)
        self.settings.boost_daily_cap = cap
        self.settings.tesseract_path = self.tess_entry.get().strip() or self.settings.tesseract_path
        self.settings.languages = LANGS.get(self.lang_menu.get(), self.settings.languages)
        self.settings.auto_language = self.auto_lang_var.get()
        self.settings.watch_inbox = self.watch_var.get()
        self.settings.api_enabled = self.api_var.get()
        self.settings.api_port = port
        self.settings.tray_enabled = self.tray_var.get()
        self.settings.auto_update = self.auto_update_var.get()
        self.settings.update_repo = self.repo_entry.get().strip()
        self.settings.save()
        if interfaces_changed:
            self.save_status.configure(
                text="✅ Saved. (Watch-inbox / Local API changes apply after restart.)",
                text_color=theme.SUCCESS)
        else:
            self.save_status.configure(text="✅ Saved.", text_color=theme.SUCCESS)
        if self.on_saved:
            self.on_saved()

    def _send_now(self) -> None:
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
