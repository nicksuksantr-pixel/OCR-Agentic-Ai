"""Jobs tab UI — grouped job browser: search, image preview, overlay viewer,
open-folder, export, label and archive. UI only — logic lives in the service."""
from tkinter import filedialog, messagebox

import customtkinter as ctk
from PIL import Image

from src.core.config.settings import Settings
from src.features.jobs import service

PREVIEW_MAX = (360, 230)   # job preview thumbnail box
OVERLAY_MAX = (1100, 720)  # overlay viewer window canvas


class JobsView(ctk.CTkFrame):
    """The Jobs tab: grouped job list (left) + rich detail panel (right)."""

    def __init__(self, master, settings: Settings):
        super().__init__(master, fg_color="transparent")
        self.settings = settings
        self.expanded: set[str] = set()
        self.search_term: str = ""
        self.current_job: dict | None = None
        self._preview_image = None  # keep a reference or Tk drops it

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # --- toolbar ---
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=0, column=0, columnspan=2, sticky="we", padx=16, pady=(16, 8))
        ctk.CTkButton(bar, text="↻ Refresh", width=90,
                      command=self.refresh).pack(side="left")
        self.search_entry = ctk.CTkEntry(bar, width=220,
                                         placeholder_text="search text / file / label")
        self.search_entry.pack(side="left", padx=(12, 4))
        self.search_entry.bind("<Return>", lambda e: self._search())
        ctk.CTkButton(bar, text="🔍", width=40, command=self._search).pack(side="left")
        ctk.CTkButton(bar, text="✖", width=40,
                      command=self._clear_search).pack(side="left", padx=(4, 0))
        ctk.CTkButton(bar, text="📂 Data folder", width=120,
                      command=service.open_data_folder).pack(side="left", padx=(12, 0))
        self.boost_label = ctk.CTkLabel(bar, text="", anchor="e")
        self.boost_label.pack(side="right")

        # --- left: job list ---
        self.job_list = ctk.CTkScrollableFrame(self, width=300)
        self.job_list.grid(row=1, column=0, padx=(16, 8), pady=(0, 16), sticky="nsw")

        # --- right: detail panel ---
        panel = ctk.CTkFrame(self)
        panel.grid(row=1, column=1, padx=(8, 16), pady=(0, 16), sticky="nsew")
        panel.grid_columnconfigure(0, weight=1)
        panel.grid_rowconfigure(4, weight=1)

        self.info_label = ctk.CTkLabel(panel, text="Select a job on the left.",
                                       anchor="w", justify="left")
        self.info_label.grid(row=0, column=0, sticky="we", padx=12, pady=(10, 4))

        name_row = ctk.CTkFrame(panel, fg_color="transparent")
        name_row.grid(row=1, column=0, sticky="we", padx=12)
        ctk.CTkLabel(name_row, text="🏷").pack(side="left")
        self.label_entry = ctk.CTkEntry(name_row, width=260,
                                        placeholder_text="name this job (optional)")
        self.label_entry.pack(side="left", padx=6)
        ctk.CTkButton(name_row, text="Save", width=60,
                      command=self._save_label).pack(side="left")

        btn_row = ctk.CTkFrame(panel, fg_color="transparent")
        btn_row.grid(row=2, column=0, sticky="we", padx=12, pady=6)
        for text, cmd in (("📂 Open folder", self._open_folder),
                          ("👁 Overlay", self._overlay),
                          ("📋 Copy text", self._copy_text),
                          ("📤 Export .txt", lambda: self._export("txt")),
                          ("📤 .json", lambda: self._export("json")),
                          ("🗑 Archive", self._archive)):
            ctk.CTkButton(btn_row, text=text, width=10, command=cmd).pack(
                side="left", padx=(0, 6))

        self.preview_label = ctk.CTkLabel(panel, text="")
        self.preview_label.grid(row=3, column=0, padx=12, pady=(2, 4))

        self.detail = ctk.CTkTextbox(panel, wrap="word")
        self.detail.grid(row=4, column=0, padx=12, pady=(0, 12), sticky="nsew")

        self.refresh()

    # ------------------------------------------------------------------ list

    def refresh(self) -> None:
        """Rebuild the left list (grouped by Source, or flat search results)."""
        for child in self.job_list.winfo_children():
            child.destroy()
        if self.search_term:
            results = service.search(self.search_term)
            ctk.CTkLabel(self.job_list, text=f"🔍 {len(results)} match(es)",
                         anchor="w").pack(fill="x", pady=(0, 4))
            for job in results:
                self._job_row(job, show_name=True)
        else:
            for group in service.grouped_jobs():
                jobs = group["jobs"]
                if len(jobs) == 1 and service.page_of(jobs[0]) is None:
                    self._job_row(jobs[0], show_name=True)
                    continue
                self._group_header(group)
                if group["source"] in self.expanded:
                    for job in jobs:
                        self._job_row(job)
        pending = service.boost_pending()
        self.boost_label.configure(
            text=f"🕓 AI Boost queue: {pending} pending" if pending else "AI Boost queue empty")

    def _group_header(self, group: dict) -> None:
        jobs = group["jobs"]
        open_ = group["source"] in self.expanded
        done = sum(1 for j in jobs if j["status"] == "done")
        text = f'{"▼" if open_ else "▶"} 📄 {group["name"][:22]} ({done}/{len(jobs)} pages)'
        ctk.CTkButton(self.job_list, text=text, anchor="w",
                      fg_color=("gray75", "gray28"),
                      command=lambda s=group["source"]: self._toggle(s)).pack(fill="x", pady=(4, 1))

    def _job_row(self, job: dict, show_name: bool = False) -> None:
        icon = {"done": "✅", "error": "❌"}.get(job["status"], "⏳")
        page = service.page_of(job)
        if job.get("label"):
            name = job["label"][:24]
        elif show_name:
            name = job["source_path"].replace("\\", "/").rsplit("/", 1)[-1][:24]
        else:
            name = f"page {page}" if page else f"job {job['id']}"
        conf = f' · {job["mean_conf"]:.0f}%' if job["mean_conf"] is not None else ""
        ctk.CTkButton(self.job_list, text=f'{icon} #{job["id"]} {name}{conf}',
                      anchor="w", fg_color="transparent",
                      command=lambda j=job["id"]: self._show(j)).pack(fill="x", pady=1)

    def _toggle(self, source: str) -> None:
        self.expanded.symmetric_difference_update({source})
        self.refresh()

    def _search(self) -> None:
        self.search_term = self.search_entry.get().strip()
        self.refresh()

    def _clear_search(self) -> None:
        self.search_term = ""
        self.search_entry.delete(0, "end")
        self.refresh()

    # ---------------------------------------------------------------- detail

    def _show(self, job_id: int) -> None:
        """Render one job: info, label, image preview and stitched text."""
        job = service.job_detail(job_id)
        if job is None:
            return
        self.current_job = job
        page = service.page_of(job)
        info = (f'Job #{job["id"]}{f" · page {page}" if page else ""}'
                f' · {job["created_at"]} · {job["status"]}'
                f' · confidence {job["mean_conf"]}%\nSource: {job["source_path"]}')
        self.info_label.configure(text=info)
        self.label_entry.delete(0, "end")
        if job.get("label"):
            self.label_entry.insert(0, job["label"])

        self._set_preview(job)

        lines = []
        flagged = [s for s in job["sections"] if s["status"] not in ("ok", "boosted")]
        if flagged:
            lines.append("Sections needing AI Boost: "
                         + ", ".join(f'#{s["idx"]} ({s["status"]})' for s in flagged))
            lines.append("")
        lines.append(job["full_text"] or "(no text)")
        self.detail.delete("1.0", "end")
        self.detail.insert("1.0", "\n".join(lines))

    def _set_preview(self, job: dict) -> None:
        path = service.original_image_path(job)
        if path is None:
            self.preview_label.configure(image=None, text="(no image preview)")
            self._preview_image = None
            return
        img = Image.open(path)
        img.thumbnail(PREVIEW_MAX)
        self._preview_image = ctk.CTkImage(img, size=img.size)
        self.preview_label.configure(image=self._preview_image, text="")

    # --------------------------------------------------------------- actions

    def _need_job(self) -> dict | None:
        if self.current_job is None:
            messagebox.showinfo("Jobs", "Select a job first.", parent=self)
        return self.current_job

    def _save_label(self) -> None:
        job = self._need_job()
        if job:
            service.rename_job(job["id"], self.label_entry.get())
            self.refresh()

    def _open_folder(self) -> None:
        job = self._need_job()
        if job and not service.open_job_folder(job["id"]):
            messagebox.showwarning("Jobs", "Job folder not found.", parent=self)

    def _copy_text(self) -> None:
        job = self._need_job()
        if job:
            self.clipboard_clear()
            self.clipboard_append(job["full_text"] or "")
            self.info_label.configure(text=self.info_label.cget("text").split("\n")[0]
                                      + "\n📋 Text copied to clipboard.")

    def _export(self, fmt: str) -> None:
        job = self._need_job()
        if not job:
            return
        source = job["source_path"].split("#page=")[0]
        name = source.replace("\\", "/").rsplit("/", 1)[-1].rsplit(".", 1)[0]
        dest = filedialog.asksaveasfilename(
            defaultextension=f".{fmt}", initialfile=f"{name}_extract.{fmt}",
            filetypes=[(fmt.upper(), f"*.{fmt}")], parent=self)
        if not dest:
            return
        pages = (service.export_text(source, dest) if fmt == "txt"
                 else service.export_json(source, dest))
        messagebox.showinfo("Export", f"Exported {pages} page(s) to:\n{dest}", parent=self)

    def _archive(self) -> None:
        job = self._need_job()
        if not job:
            return
        if not messagebox.askyesno(
                "Archive job",
                f'Archive job #{job["id"]}?\n\nIt disappears from the list and its '
                "folder moves to jobs\\_trash (nothing is deleted).", parent=self):
            return
        service.archive_job(job["id"])
        self.current_job = None
        self.info_label.configure(text="Job archived (folder in jobs\\_trash).")
        self.preview_label.configure(image=None, text="")
        self._preview_image = None
        self.detail.delete("1.0", "end")
        self.refresh()

    def _overlay(self) -> None:
        """Render word boxes coloured by confidence and show them in a window."""
        job = self._need_job()
        if not job:
            return
        self.info_label.configure(text=self.info_label.cget("text").split("\n")[0]
                                  + "\n👁 Rendering overlay...")
        self.update_idletasks()
        out = service.render_overlay(job["id"], self.settings.upscale_min_side)
        if out is None:
            messagebox.showwarning("Overlay", "No original image for this job.", parent=self)
            return
        win = ctk.CTkToplevel(self)
        win.title(f'Overlay — job #{job["id"]} (green ≥75 · yellow ≥60 · red <60) — saved {out.name}')
        img = Image.open(out)
        img.thumbnail(OVERLAY_MAX)
        photo = ctk.CTkImage(img, size=img.size)
        label = ctk.CTkLabel(win, image=photo, text="")
        label.image = photo  # keep alive
        label.pack(padx=8, pady=8)
        win.after(200, win.lift)
        self.info_label.configure(text=self.info_label.cget("text").replace(
            "\n👁 Rendering overlay...", f"\n👁 Overlay saved: {out}"))
