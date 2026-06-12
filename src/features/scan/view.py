"""Scan tab UI — pick a Source, watch progress, read the stitched result. UI only."""
from tkinter import filedialog

import customtkinter as ctk
from PIL import Image

from src.core.config import paths
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

        self.status = ctk.CTkLabel(self, text="Ready.", anchor="w")
        self.status.pack(fill="x", padx=16)

        self.result_box = ctk.CTkTextbox(self, wrap="word")
        self.result_box.pack(fill="both", expand=True, padx=16, pady=(8, 16))

        err = controller.engine_ready()
        if err:
            self.status.configure(text=f"⚠ {err}")
            self.pick_btn.configure(state="disabled")

    def _pick(self) -> None:
        """Open the file dialog and kick off a scan."""
        path = filedialog.askopenfilename(filetypes=FILETYPES)
        if not path:
            return
        self.pick_btn.configure(state="disabled")
        self._set_status("Starting...")
        self.result_box.delete("1.0", "end")
        self.controller.scan_file(
            path,
            on_progress=lambda msg: self.after(0, self._set_status, msg),
            on_done=lambda results: self.after(0, self._show_results, results),
            on_error=lambda msg: self.after(0, self._show_error, msg),
        )

    def _set_status(self, msg: str) -> None:
        self.status.configure(text=msg)

    def _show_results(self, results) -> None:
        """Render the finished Raw Extract(s) — one block per Job (PDF page)."""
        queued = sum(1 for r in results for s in r.sections
                     if s.status in ("low_conf", "unreadable"))
        jobs = ", ".join(str(r.job_id) for r in results)
        conf = round(sum(r.mean_conf for r in results) / len(results), 1)
        self._set_status(
            f"✅ Job(s) {jobs} done — confidence {conf}%"
            + (f" · {queued} section(s) queued for AI Boost" if queued else ""))
        blocks = []
        for r in results:
            header = f"--- Page {r.page}/{r.pages} (job {r.job_id}) ---\n" if r.page else ""
            blocks.append(header + (r.full_text or "(no text found)"))
        self.result_box.insert("1.0", "\n\n".join(blocks))
        self.pick_btn.configure(state="normal")
        if self.on_job_done:
            for r in results:
                self.on_job_done(r)

    def _show_error(self, msg: str) -> None:
        self._set_status(f"❌ {msg}")
        self.pick_btn.configure(state="normal")
