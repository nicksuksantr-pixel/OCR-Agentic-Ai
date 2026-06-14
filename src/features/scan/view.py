"""Scan tab UI — pick a Source, watch progress, read the stitched result.

UI only. Adds (v0.2.0) recoverable banners: when Tesseract isn't found the Scan
button is no longer a dead end (Re-check / Open Settings), and an AI-Boost-without
-a-key warning is shown persistently instead of vanishing off a status line.
"""
from tkinter import filedialog

import customtkinter as ctk
from PIL import Image, ImageDraw

from src.core.config import paths
from src.core.config.settings import Settings
from src.core.services import engine, gemini, store
from src.core.utils import pdfio
from src.features.scan.controller import ScanController
from src.shared.ui import theme, widgets

FILETYPES = [("Images / PDF", "*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp *.pdf"),
             ("All files", "*.*")]

PREVIEW_W = 440          # live-preview pane width (px)
PREVIEW_H = 560          # height cap so a tall page never overflows a short window
PREVIEW_HINT = "📄 A live preview of the page appears here while scanning,\n" \
               "with the section being read highlighted."
HILITE = (61, 125, 255)  # theme.PRIMARY (#3d7dff) as RGB — the main-grid section box
OFFSET_HILITE = (230, 70, 70)  # red — the staggered offset grid (Nick's blue+red dual grid)


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

        # The Scan tab gets its own moving progress bar (v0.2.2) — previously it
        # had only a one-line status, while the Dashboard owned the bar.
        self.progress_bar = ctk.CTkProgressBar(self, height=8, progress_color=theme.PRIMARY)
        self.progress_bar.pack(fill="x", padx=theme.L, pady=(0, theme.S))
        self.progress_bar.set(0)

        # Body: live page preview (left) + streamed text (right). This fills what
        # used to be one big empty box for the whole multi-minute page — now it
        # shows the page with the current section highlighted and streams each
        # section's words as they are read (Nick, v0.2.2).
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=theme.L, pady=(0, theme.L))
        body.grid_columnconfigure(0, minsize=PREVIEW_W + 2 * theme.M, weight=0)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)

        self.preview_card = ctk.CTkFrame(body, fg_color=theme.CARD, corner_radius=10)
        self.preview_card.grid(row=0, column=0, sticky="nsew", padx=(0, theme.S))
        self.preview_label = ctk.CTkLabel(
            self.preview_card, text=PREVIEW_HINT, text_color=theme.MUTED,
            font=theme.font_caption(), wraplength=PREVIEW_W - 24)
        self.preview_label.pack(fill="both", expand=True, padx=theme.M, pady=theme.M)

        self.result_box = ctk.CTkTextbox(body, wrap="word", font=theme.font_body(),
                                         fg_color=theme.CARD, corner_radius=10)
        self.result_box.grid(row=0, column=1, sticky="nsew")

        # Live-feed state (reset on every new pick).
        self._final = ""            # finished pages' clean stitched text
        self._live_lines = []       # current page's per-section snippets
        self._live_header = ""      # "Scanning page X..." banner above the live lines
        self._preview_base = None   # PIL thumbnail of the current page (no highlight)
        self._preview_ctk = None    # keep a ref so the CTkImage isn't GC'd
        self._pscale = (1.0, 1.0)   # orig→display scale for the bbox highlight

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
        # At most one banner shows (engine-missing already returned above). A
        # missing selected OCR model is informational, not a hard block — the
        # default is tha+eng and an English page reads on eng alone, so we inform
        # and let the scan proceed (the pipeline now falls back to the installed
        # languages). It takes priority over the AI-Boost-key warning (v0.2.6).
        missing_langs = self._missing_languages()
        if missing_langs:
            names = ", ".join(f"'{m}'" for m in missing_langs)
            self._show_banner(
                f"⚠ Language {names} is selected but not installed — those pages "
                "may read poorly; English pages still scan on 'eng'. "
                "Add the model or switch language in Settings.", theme.WARN,
                [("⚙ Open Settings", self._open_settings)])
        elif self.settings.ai_boost_enabled and not gemini.read_api_key():
            self._show_banner(
                "⚠ AI Boost is ON but no Gemini key is set — unclear sections will "
                "queue but never be processed.", theme.WARN,
                [("⚙ Open Settings", self._open_settings)])
        else:
            self.banner.pack_forget()

    def _missing_languages(self) -> list[str]:
        """Selected OCR languages tesseract can't load right now (engine already
        confirmed ready). Empty when all are installed OR the language list can't
        be read (don't cry wolf on an unknowable state) — installed .exe bundles
        tha, so end users never see this; it guards portable/dev runs (v0.2.6)."""
        installed = set(engine.available_languages())
        if not installed:
            return []
        return [lang for lang in self.settings.languages.split("+")
                if lang not in installed]

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
            if done and widgets.ask_yesno(
                    self, "Resume batch",
                    f"{len(done)} page(s) of this PDF are already scanned.\n\n"
                    "Skip them and continue where it stopped?"):
                skip_pages = done
        elif self._already_scanned(path):
            # Single image already in the library — offer to skip a re-scan (the
            # deep-detail pass is minutes; v0.2.2 mirrors the PDF resume prompt).
            if not widgets.ask_yesno(
                    self, "Already scanned",
                    "This image is already in your library.\n\nScan it again?"):
                return
        self.pick_btn.configure(state="disabled")
        self.pause_btn.configure(state="normal", text="⏸ Pause")
        self.cancel_btn.configure(state="normal")
        self._cancel_requested = False
        self._set_status("Starting...")
        self._reset_feed()
        self.controller.scan_file(
            path,
            on_progress=lambda msg: self.after(0, self._set_status, msg),
            on_page_done=lambda r: self.after(0, self._show_page, r),
            on_done=lambda results: self.after(0, self._show_results, results),
            on_error=lambda msg: self.after(0, self._show_error, msg),
            on_event=lambda e: self.after(0, self._on_event, e),
            skip_pages=skip_pages,
        )

    def _already_scanned(self, path: str) -> bool:
        """True when this exact image already has a finished job (re-scan guard).

        include_archived=True so an ARCHIVED copy still prompts a re-scan, the
        same way a PDF page that was archived is skipped on resume (done_pages
        counts archived pages). Without this, an archived image was invisible
        here and got silently re-scanned into a brand-new job (v0.2.6 parity)."""
        for variant in {path, path.replace("\\", "/"), path.replace("/", "\\")}:
            if any(j["status"] == "done"
                   for j in store.jobs_for_exact_source(variant, include_archived=True)):
                return True
        return False

    def _set_status(self, msg: str) -> None:
        self.status.configure(text=msg)

    # ----------------------------------------------------- live feed (v0.2.2)

    def _reset_feed(self) -> None:
        """Clear the streamed text, progress bar and preview for a fresh scan."""
        self._final = ""
        self._live_lines, self._live_header = [], ""
        self.result_box.delete("1.0", "end")
        self.progress_bar.set(0)
        self._clear_preview()

    def _clear_preview(self) -> None:
        self._preview_base = None
        self._preview_ctk = None
        self.preview_label.configure(image=None, text=PREVIEW_HINT, text_color=theme.MUTED)

    def _on_event(self, e: dict) -> None:
        """Render one live pipeline event (already marshalled onto the Tk thread)."""
        kind = e.get("kind")
        if kind == "page_ready":
            self._begin_page(e)
        elif kind == "section":
            self._highlight_section(e)
            self._set_scan_progress(e)
        elif kind == "offset":
            self._highlight_offset(e)
        elif kind == "section_text":
            self._add_live_text(e)

    def _begin_page(self, e: dict) -> None:
        """A new page's upright image arrived — show it and start its live feed."""
        img = e.get("image")
        if img is None:
            return
        disp = img.copy()
        disp.thumbnail((PREVIEW_W, PREVIEW_H))
        ow, oh = e.get("size", (img.width, img.height))
        self._pscale = (disp.width / ow, disp.height / oh)
        self._preview_base = disp
        self._show_preview(disp)
        self._live_lines = []
        self._live_header = (f"⏳ Scanning page {e.get('page', 1)}/{e.get('pages', 1)} "
                             f"— {e.get('sections', 0)} sections")
        self._render_text()

    def _show_preview(self, pil: Image.Image) -> None:
        self._preview_ctk = ctk.CTkImage(pil, size=(pil.width, pil.height))
        self.preview_label.configure(image=self._preview_ctk, text="")

    def _highlight_section(self, e: dict) -> None:
        """Draw the box of the section currently being read onto the preview."""
        if self._preview_base is None:
            return
        bx, by, bw, bh = e.get("bbox", (0, 0, 0, 0))
        sx, sy = self._pscale
        im = self._preview_base.convert("RGB")  # returns a copy — base stays clean
        ImageDraw.Draw(im).rectangle(
            [bx * sx, by * sy, (bx + bw) * sx, (by + bh) * sy], outline=HILITE, width=3)
        self._show_preview(im)

    def _highlight_offset(self, e: dict) -> None:
        """Draw the offset-grid tile currently being read, in red — so the
        staggered second pass is visibly distinct from the blue main grid (Nick's
        blue+red dual grid; the cut it straddles sat between two blue boxes)."""
        if self._preview_base is None:
            return
        bx, by, bw, bh = e.get("bbox", (0, 0, 0, 0))
        sx, sy = self._pscale
        im = self._preview_base.convert("RGB")  # returns a copy — base stays clean
        ImageDraw.Draw(im).rectangle(
            [bx * sx, by * sy, (bx + bw) * sx, (by + bh) * sy], outline=OFFSET_HILITE, width=3)
        self._show_preview(im)

    def _set_scan_progress(self, e: dict) -> None:
        sections, pages = e.get("sections") or 0, e.get("pages") or 1
        page = e.get("page") or 1
        if sections:
            frac = ((page - 1) + e.get("idx", 0) / sections) / pages
            self.progress_bar.set(min(max(frac, 0.0), 1.0))

    def _add_live_text(self, e: dict) -> None:
        text = (e.get("text") or "").strip()
        snippet = text if len(text) <= 240 else text[:240] + "…"
        idx, sections = e.get("idx", 0), e.get("sections", 0)
        self._live_lines.append(f"[{idx + 1}/{sections}] {snippet or '— (no text)'}")
        self._render_text()

    def _render_text(self) -> None:
        """Result box = finished pages' clean text + the current page's live feed."""
        parts = []
        if self._final:
            parts.append(self._final)
        if self._live_header or self._live_lines:
            parts.append(self._live_header + "\n" + "\n".join(self._live_lines))
        self.result_box.delete("1.0", "end")
        self.result_box.insert("1.0", "\n\n".join(parts))
        self.result_box.see("end")

    def _show_page(self, r) -> None:
        """A whole Job (PDF page) finished — fold its clean stitched text into the
        result, clear the live feed, and report confidence."""
        queued = sum(1 for s in r.sections if s.status in ("low_conf", "unreadable"))
        header = (f"--- Page {r.page}/{r.pages} (job {r.job_id}) ---"
                  if r.page else f"--- Job {r.job_id} ---")
        block = header + "\n" + (r.full_text or "(no text found)")
        self._final = f"{self._final}\n\n{block}" if self._final else block
        self._live_lines, self._live_header = [], ""
        self._render_text()
        label = f"Page {r.page}/{r.pages}" if r.page else f"Job {r.job_id}"
        if getattr(r, "no_text", False):
            self._set_status(f"✅ {label} done — no readable text found (blank page or photo).")
        else:
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
            self.progress_bar.set(1.0)
        else:
            self._set_status("No pages produced.")
        self._reset_buttons()

    def _show_error(self, msg: str) -> None:
        self._set_status(f"❌ {msg}")
        self.progress_bar.set(0)
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
