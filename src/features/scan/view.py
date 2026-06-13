"""Scan tab UI — pick a Source, watch progress, read the stitched result.

UI only. Adds (v0.2.0) recoverable banners: when Tesseract isn't found the Scan
button is no longer a dead end (Re-check / Open Settings), and an AI-Boost-without
-a-key warning is shown persistently instead of vanishing off a status line.
"""
from tkinter import filedialog, messagebox

import customtkinter as ctk
from PIL import Image

from src.core.config import paths
from src.core.config.settings import Settings
from src.core.services import gemini, store
from src.core.utils import pdfio
from src.features.scan.controller import ScanController
from src.shared.ui import theme

FILETYPES = [("Images / PDF", "*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp *.pdf"),
             ("All files", "*.*")]


class ScanView(ctk.CTkFrame):
    """The Scan tab: select-file + progress + streamed result text."""

    def __init__(self, master, controller: ScanController, settings: Settings,
                 on_job_done=None, on_open_settings=None):
        super().__init__(master, fg_color="transparent")
        self.controller = controller
        self.settings = settings
        self.on_job_done = on_job_done           # App hook — e.g. auto AI Boost
        self.on_open_settings = on_open_settings  # App hook — jump to the Settings tab
        self._cancel_requested = False

        # Welcome row: Scout the mascot (helper role #3) + the pick/pause/cancel
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=theme.L, pady=(theme.L, theme.S))
        mascot_path = paths.asset("mascot.png")
        if mascot_path.exists():
            mascot = ctk.CTkImage(Image.open(mascot_path), size=(60, 60))
            ctk.CTkLabel(top, image=mascot, text="").pack(side="left", padx=(0, theme.M))
        self.pick_btn = ctk.CTkButton(top, text="📄  Select image or PDF to scan",
                                      height=46, font=theme.font_h2(),
                                      command=self._pick, **theme.primary_btn())
        self.pick_btn.pack(side="left", fill="x", expand=True)
        self.pause_btn = ctk.CTkButton(top, text="⏸ Pause", width=96, height=46,
                                       state="disabled", command=self._toggle_pause,
                                       **theme.ghost_btn())
        self.pause_btn.pack(side="left", padx=(theme.S, 0))
        self.cancel_btn = ctk.CTkButton(top, text="✖ Cancel", width=96, height=46,
                                        state="disabled", command=self._cancel,
                                        **theme.danger_btn())
        self.cancel_btn.pack(side="left", padx=(theme.S, 0))

        # Banner area (engine / key warnings) — packed only when there's a problem.
        self.banner = ctk.CTkFrame(self, fg_color=theme.CARD, corner_radius=8)
        self.banner_label = ctk.CTkLabel(self.banner, text="", anchor="w",
                                         justify="left", wraplength=620)
        self.banner_label.pack(side="left", fill="x", expand=True, padx=theme.M, pady=theme.S)
        self.banner_btns = ctk.CTkFrame(self.banner, fg_color="transparent")
        self.banner_btns.pack(side="right", padx=theme.S)

        self.status = ctk.CTkLabel(self, text="Ready.", anchor="w", text_color=theme.MUTED)
        self.status.pack(fill="x", padx=theme.L, pady=(0, theme.XS))

        self.result_box = ctk.CTkTextbox(self, wrap="word", font=theme.font_body(),
                                         fg_color=theme.CARD, corner_radius=10)
        self.result_box.pack(fill="both", expand=True, padx=theme.L, pady=(0, theme.L))

        self.refresh_banners()

    # ---------------------------------------------------------------- banners

    def refresh_banners(self) -> None:
        """Re-evaluate engine + key warnings (called on build and after settings
        save / a Re-check)."""
        for w in self.banner_btns.winfo_children():
            w.destroy()
        err = self.controller.engine_ready()
        if err:
            self.pick_btn.configure(state="disabled")
            self._show_banner(f"⚠ {err}", theme.WARN, [
                ("🔁 Re-check engine", self._recheck_engine),
                ("⚙ Open Settings", self._open_settings)])
            return
        self.pick_btn.configure(state="normal" if not self.controller.busy else "disabled")
        if self.settings.ai_boost_enabled and not gemini.read_api_key():
            self._show_banner(
                "⚠ AI Boost is ON but no Gemini key is set — unclear sections will "
                "queue but never be processed.", theme.WARN,
                [("⚙ Open Settings", self._open_settings)])
        else:
            self.banner.pack_forget()

    def _show_banner(self, text: str, color: str, buttons: list) -> None:
        self.banner_label.configure(text=text, text_color=color)
        for label, cmd in buttons:
            ctk.CTkButton(self.banner_btns, text=label, width=130, height=28,
                          command=cmd, **theme.ghost_btn()).pack(side="left", padx=theme.XS)
        # Sits between the top action row and the status line.
        self.banner.pack(fill="x", padx=theme.L, pady=(0, theme.S), before=self.status)

    def _recheck_engine(self) -> None:
        self.refresh_banners()
        if not self.controller.engine_ready():
            self._set_status("✅ Engine ready.")

    def _open_settings(self) -> None:
        if self.on_open_settings:
            self.on_open_settings()

    # ------------------------------------------------------------------ scan

    def _pick(self) -> None:
        """Open the file dialog and kick off a scan (offering batch resume)."""
        path = filedialog.askopenfilename(filetypes=FILETYPES)
        if not path:
            return
        skip_pages = None
        if pdfio.is_pdf(path):
            done = store.done_pages(path.replace("\\", "/"))
            done |= store.done_pages(path.replace("/", "\\"))
            if done and messagebox.askyesno(
                    "Resume batch",
                    f"{len(done)} page(s) of this PDF are already scanned.\n\n"
                    "Skip them and continue where it stopped?", parent=self):
                skip_pages = done
        self.pick_btn.configure(state="disabled")
        self.pause_btn.configure(state="normal", text="⏸ Pause")
        self.cancel_btn.configure(state="normal")
        self._cancel_requested = False
        self._set_status("Starting...")
        self.result_box.delete("1.0", "end")
        self.controller.scan_file(
            path,
            on_progress=lambda msg: self.after(0, self._set_status, msg),
            on_page_done=lambda r: self.after(0, self._show_page, r),
            on_done=lambda results: self.after(0, self._show_results, results),
            on_error=lambda msg: self.after(0, self._show_error, msg),
            skip_pages=skip_pages,
        )

    def _set_status(self, msg: str) -> None:
        self.status.configure(text=msg)

    def _show_page(self, r) -> None:
        """Stream one finished Job (PDF page) into the result box immediately."""
        queued = sum(1 for s in r.sections if s.status in ("low_conf", "unreadable"))
        header = f"--- Page {r.page}/{r.pages} (job {r.job_id}) ---\n" if r.page else ""
        self.result_box.insert("end", header + (r.full_text or "(no text found)") + "\n\n")
        label = f"Page {r.page}/{r.pages}" if r.page else f"Job {r.job_id}"
        self._set_status(
            f"✅ {label} done — confidence {r.mean_conf}%"
            + (f" · {queued} section(s) queued for AI Boost" if queued else ""))
        if self.on_job_done:
            self.on_job_done(r)

    def _show_results(self, results) -> None:
        """Whole Source finished (or cancelled) — final summary."""
        if self._cancel_requested:
            self._set_status(f"⏹ Cancelled — {len(results)} finished page(s) kept.")
        elif results:
            jobs = ", ".join(str(r.job_id) for r in results)
            conf = round(sum(r.mean_conf for r in results) / len(results), 1)
            self._set_status(f"✅ All done — job(s) {jobs}, overall confidence {conf}%")
        else:
            self._set_status("No pages produced.")
        self._reset_buttons()

    def _show_error(self, msg: str) -> None:
        self._set_status(f"❌ {msg}")
        self._reset_buttons()

    def _reset_buttons(self) -> None:
        self.pick_btn.configure(state="normal")
        self.pause_btn.configure(state="disabled", text="⏸ Pause")
        self.cancel_btn.configure(state="disabled")

    def _toggle_pause(self) -> None:
        if self.controller.paused:
            self.controller.resume()
            self.pause_btn.configure(text="⏸ Pause")
            self._set_status("Resumed.")
        else:
            self.controller.pause()
            self.pause_btn.configure(text="▶ Resume")
            self._set_status("⏸ Paused (finishing the current step)...")

    def _cancel(self) -> None:
        self._cancel_requested = True
        self.controller.cancel()
        self.pause_btn.configure(state="disabled")
        self._set_status("Cancelling after the current step...")
