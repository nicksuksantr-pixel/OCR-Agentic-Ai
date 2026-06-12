"""Scan tab UI — pick a Source, watch progress, read the stitched result. UI only."""
from tkinter import filedialog, messagebox

import customtkinter as ctk
from PIL import Image

from src.core.config import paths
from src.core.services import store
from src.core.utils import pdfio
from src.features.scan.controller import ScanController

FILETYPES = [("Images / PDF", "*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp *.pdf"),
             ("All files", "*.*")]


class ScanView(ctk.CTkFrame):
    """The Scan tab: select-file button + progress label + result textbox."""

    def __init__(self, master, controller: ScanController, on_job_done=None):
        super().__init__(master, fg_color="transparent")
        self.controller = controller
        self.on_job_done = on_job_done  # App hook — e.g. auto-trigger AI Boost

        # Welcome row: Scout the mascot (helper role, branding #3) + the pick button
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=16, pady=(16, 8))
        mascot_path = paths.asset("mascot.png")
        if mascot_path.exists():
            mascot = ctk.CTkImage(Image.open(mascot_path), size=(64, 64))
            ctk.CTkLabel(top, image=mascot, text="").pack(side="left", padx=(0, 10))
        self.pick_btn = ctk.CTkButton(top, text="📄  Select image or PDF to scan",
                                      height=48, command=self._pick)
        self.pick_btn.pack(side="left", fill="x", expand=True)
        self.pause_btn = ctk.CTkButton(top, text="⏸ Pause", width=92, height=48,
                                       state="disabled", command=self._toggle_pause)
        self.pause_btn.pack(side="left", padx=(8, 0))
        self.cancel_btn = ctk.CTkButton(top, text="✖ Cancel", width=92, height=48,
                                        state="disabled", fg_color="#8a3333",
                                        hover_color="#a04040", command=self._cancel)
        self.cancel_btn.pack(side="left", padx=(8, 0))
        self._cancel_requested = False

        self.status = ctk.CTkLabel(self, text="Ready.", anchor="w")
        self.status.pack(fill="x", padx=16)

        self.result_box = ctk.CTkTextbox(self, wrap="word")
        self.result_box.pack(fill="both", expand=True, padx=16, pady=(8, 16))

        err = controller.engine_ready()
        if err:
            self.status.configure(text=f"⚠ {err}")
            self.pick_btn.configure(state="disabled")

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
        """Stream one finished Job (PDF page) into the result box immediately —
        no waiting for the rest of the batch."""
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
