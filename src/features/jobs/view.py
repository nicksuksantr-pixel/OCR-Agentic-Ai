"""Jobs tab UI — grouped job browser: search, multi-select, image preview,
overlay viewer, open-folder, export, label, archive and delete.

UI only — all logic lives in the service, and every heavy operation (DB queries,
image decode, overlay render, export, delete) runs on a worker thread via
JobsController so the tab never freezes (v0.2.0 redesign; before this everything
ran on the Tk main thread and the window 'hung / wouldn't refresh').
"""
import tkinter
from tkinter import filedialog, messagebox

import customtkinter as ctk
from PIL import Image

from src.core.config.settings import Settings
from src.features.jobs import service
from src.features.jobs.controller import JobsController
from src.shared.ui import theme
from src.shared.ui.widgets import add_tooltip

PREVIEW_MAX = (360, 230)   # job preview thumbnail box
OVERLAY_MAX = (1100, 720)  # overlay viewer window canvas


class JobsView(ctk.CTkFrame):
    """The Jobs tab: grouped, multi-selectable job list (left) + detail (right)."""

    def __init__(self, master, settings: Settings):
        super().__init__(master, fg_color="transparent")
        self.settings = settings
        self.controller = JobsController(settings)
        self.expanded: set[str] = set()
        self.search_term: str = ""
        self.current_job: dict | None = None
        self.selected: set[int] = set()      # job ids ticked for bulk actions
        self._preview_image = None           # keep a ref or Tk drops it
        self._gen = 0                         # newest-load wins (drop stale rebuilds)
        self._refresh_pending = False

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(2, weight=1)

        self._build_toolbar()
        self._build_selection_bar()
        self._build_list()
        self._build_detail()
        self._set_actions_enabled(False)
        self.refresh()

    def _post(self, fn, *args) -> None:
        """Marshal a worker-thread result onto the Tk thread, guarded against a
        window torn down mid-operation (the result simply drops)."""
        try:
            self.after(0, fn, *args)
        except (RuntimeError, tkinter.TclError):
            pass

    # ----------------------------------------------------------------- build

    def _build_toolbar(self) -> None:
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=0, column=0, columnspan=2, sticky="we", padx=theme.L, pady=(theme.L, theme.S))
        ctk.CTkButton(bar, text="↻ Refresh", width=92, command=self.refresh,
                      **theme.ghost_btn()).pack(side="left")
        self.search_entry = ctk.CTkEntry(bar, width=240,
                                         placeholder_text="search text / file name / label")
        self.search_entry.pack(side="left", padx=(theme.M, theme.XS))
        self.search_entry.bind("<Return>", lambda e: self._search())
        search_b = ctk.CTkButton(bar, text="🔍", width=36, command=self._search,
                                 **theme.ghost_btn())
        search_b.pack(side="left")
        add_tooltip(search_b, "Search")
        clear_b = ctk.CTkButton(bar, text="✖", width=36, command=self._clear_search,
                                **theme.ghost_btn())
        clear_b.pack(side="left", padx=(theme.XS, 0))
        add_tooltip(clear_b, "Clear search")
        ctk.CTkButton(bar, text="📂 Data folder", width=128,
                      command=service.open_data_folder, **theme.ghost_btn()).pack(
            side="left", padx=(theme.M, 0))
        ctk.CTkButton(bar, text="🧹 Empty trash", width=128, command=self._empty_trash,
                      **theme.ghost_btn()).pack(side="left", padx=(theme.S, 0))
        self.boost_label = ctk.CTkLabel(bar, text="", anchor="e", text_color=theme.MUTED)
        self.boost_label.pack(side="right")

    def _build_selection_bar(self) -> None:
        self.sel_bar = ctk.CTkFrame(self, fg_color=theme.CARD, corner_radius=8)
        self.sel_bar.grid(row=1, column=0, columnspan=2, sticky="we", padx=theme.L, pady=(0, theme.S))
        self.sel_label = ctk.CTkLabel(self.sel_bar, text="", anchor="w", font=theme.font_caption())
        self.sel_label.pack(side="left", padx=theme.M, pady=theme.XS)
        ctk.CTkButton(self.sel_bar, text="🗑 Delete selected", width=140, height=26,
                      command=self._delete_selected, **theme.danger_btn()).pack(
            side="right", padx=(0, theme.M), pady=theme.XS)
        ctk.CTkButton(self.sel_bar, text="🗂 Archive selected", width=140, height=26,
                      command=self._archive_selected, **theme.ghost_btn()).pack(
            side="right", padx=theme.XS, pady=theme.XS)
        ctk.CTkButton(self.sel_bar, text="Clear", width=56, height=26,
                      command=self._clear_selection, **theme.ghost_btn()).pack(
            side="right", padx=theme.XS, pady=theme.XS)
        self.sel_bar.grid_remove()  # only shown when something is ticked

    def _build_list(self) -> None:
        self.job_list = ctk.CTkScrollableFrame(self, width=320, label_text="",
                                               fg_color=theme.CARD, corner_radius=10)
        self.job_list.grid(row=2, column=0, padx=(theme.L, theme.S), pady=(0, theme.L), sticky="nsw")

    def _build_detail(self) -> None:
        panel = ctk.CTkFrame(self, fg_color=theme.CARD, corner_radius=10)
        panel.grid(row=2, column=1, padx=(theme.S, theme.L), pady=(0, theme.L), sticky="nsew")
        panel.grid_columnconfigure(0, weight=1)
        panel.grid_rowconfigure(4, weight=1)

        self.info_label = ctk.CTkLabel(panel, text="Select a job on the left to see its "
                                       "text, preview and actions.", anchor="w",
                                       justify="left", text_color=theme.MUTED)
        self.info_label.grid(row=0, column=0, sticky="we", padx=theme.M, pady=(theme.M, theme.XS))

        name_row = ctk.CTkFrame(panel, fg_color="transparent")
        name_row.grid(row=1, column=0, sticky="we", padx=theme.M)
        ctk.CTkLabel(name_row, text="🏷").pack(side="left")
        self.label_entry = ctk.CTkEntry(name_row, width=260,
                                        placeholder_text="name this job (optional)")
        self.label_entry.pack(side="left", padx=theme.S)
        self.save_label_btn = ctk.CTkButton(name_row, text="Save", width=64,
                                            command=self._save_label, **theme.ghost_btn())
        self.save_label_btn.pack(side="left")

        # Action rows — grouped: view / export / destructive. Full labels (no
        # more width=10 clipping 'Archive' down to 'Arch').
        self._actions: list[ctk.CTkButton] = []
        view_row = ctk.CTkFrame(panel, fg_color="transparent")
        view_row.grid(row=2, column=0, sticky="we", padx=theme.M, pady=(theme.S, 0))
        self._action(view_row, "📂 Open folder", self._open_folder)
        self._action(view_row, "👁 Overlay", self._overlay)
        self._action(view_row, "📋 Copy text", self._copy_text)
        self._action(view_row, "⤓ Export .txt", lambda: self._export("txt"))
        self._action(view_row, "⤓ Export .json", lambda: self._export("json"))

        danger_row = ctk.CTkFrame(panel, fg_color="transparent")
        danger_row.grid(row=3, column=0, sticky="we", padx=theme.M, pady=(theme.XS, theme.S))
        self._action(danger_row, "🗂 Archive", self._archive, ghost=True)
        self._action(danger_row, "🗑 Delete page", self._delete_page, danger=True)
        self._action(danger_row, "🗑 Delete whole file", self._delete_file, danger=True)

        self.preview_label = ctk.CTkLabel(panel, text="")
        self.preview_label.grid(row=4, column=0, padx=theme.M, pady=(theme.XS, theme.XS), sticky="n")

        self.detail = ctk.CTkTextbox(panel, wrap="word", font=theme.font_body(),
                                     fg_color="transparent")
        self.detail.grid(row=5, column=0, padx=theme.M, pady=(0, theme.M), sticky="nsew")
        panel.grid_rowconfigure(5, weight=1)

    def _action(self, parent, text: str, cmd, danger: bool = False, ghost: bool = False) -> None:
        style = theme.danger_btn() if danger else theme.ghost_btn() if ghost else theme.primary_btn()
        btn = ctk.CTkButton(parent, text=text, command=cmd, height=30, **style)
        btn.pack(side="left", padx=(0, theme.S))
        self._actions.append(btn)

    def _set_actions_enabled(self, on: bool) -> None:
        state = "normal" if on else "disabled"
        for b in self._actions:
            b.configure(state=state)
        self.save_label_btn.configure(state=state)

    # ------------------------------------------------------------------ list

    def refresh(self) -> None:
        """Coalesce rapid refreshes (a 45-page scan streams one per page) into a
        single off-thread reload."""
        if self._refresh_pending or not self.winfo_exists():
            return
        self._refresh_pending = True
        self.after(120, self._do_refresh)

    def _do_refresh(self) -> None:
        self._refresh_pending = False
        if not self.winfo_exists():
            return
        self._gen += 1
        gen, term = self._gen, self.search_term
        self.controller.run(
            lambda: self._load(term),
            lambda data: self._post(self._render_list, gen, data),
            on_error=lambda exc: self._post(self._render_error, exc))

    @staticmethod
    def _load(term: str) -> dict:
        if term:
            return {"mode": "search", "results": service.search(term),
                    "pending": service.boost_pending()}
        return {"mode": "groups", "groups": service.grouped_jobs(),
                "pending": service.boost_pending()}

    def _render_list(self, gen: int, data: dict) -> None:
        if gen != self._gen or not self.winfo_exists():
            return  # a newer refresh superseded this one
        for child in self.job_list.winfo_children():
            child.destroy()
        if data["mode"] == "search":
            results = data["results"]
            ctk.CTkLabel(self.job_list, text=f"🔍 {len(results)} match(es)", anchor="w",
                         text_color=theme.MUTED).pack(fill="x", padx=theme.S, pady=(theme.XS, theme.XS))
            for job in results:
                self._job_row(job, show_name=True)
        else:
            for group in data["groups"]:
                jobs = group["jobs"]
                if len(jobs) == 1 and service.page_of(jobs[0]) is None:
                    self._job_row(jobs[0], show_name=True)
                    continue
                self._group_header(group)
                if group["source"] in self.expanded:
                    for job in jobs:
                        self._job_row(job)
        pending = data["pending"]
        self.boost_label.configure(
            text=f"🕓 AI Boost queue: {pending} pending" if pending else "AI Boost queue empty")
        self._update_selection_bar()

    def _render_error(self, exc: Exception) -> None:
        if self.winfo_exists():
            self.info_label.configure(text=f"⚠ Could not load jobs: {exc}")

    def _group_header(self, group: dict) -> None:
        jobs = group["jobs"]
        open_ = group["source"] in self.expanded
        done = sum(1 for j in jobs if j["status"] == "done")
        row = ctk.CTkFrame(self.job_list, fg_color=theme.CARD_HI, corner_radius=6)
        row.pack(fill="x", padx=theme.XS, pady=(theme.XS, 1))
        ids = [j["id"] for j in jobs]
        var = ctk.BooleanVar(value=all(i in self.selected for i in ids))
        ctk.CTkCheckBox(row, text="", width=22, variable=var,
                        command=lambda g=ids, v=var: self._toggle_group(g, v)).pack(side="left", padx=(theme.XS, 0))
        text = f'{"▼" if open_ else "▶"} 📄 {group["name"][:24]}  ({done}/{len(jobs)} pages)'
        ctk.CTkButton(row, text=text, anchor="w", fg_color="transparent",
                      hover_color=theme.CARD, text_color=theme.TEXT,
                      command=lambda s=group["source"]: self._toggle(s)).pack(
            side="left", fill="x", expand=True)

    def _job_row(self, job: dict, show_name: bool = False) -> None:
        page = service.page_of(job)
        if job.get("label"):
            name = job["label"][:26]
        elif show_name:
            name = job["source_path"].replace("\\", "/").rsplit("/", 1)[-1][:26]
        else:
            name = f"page {page}" if page else f"job {job['id']}"
        icon = {"done": "✅", "error": "❌"}.get(job["status"], "⏳")
        conf = job["mean_conf"]
        row = ctk.CTkFrame(self.job_list, fg_color="transparent")
        row.pack(fill="x", padx=theme.XS, pady=1)
        var = ctk.BooleanVar(value=job["id"] in self.selected)
        ctk.CTkCheckBox(row, text="", width=22, variable=var,
                        command=lambda i=job["id"], v=var: self._toggle_one(i, v)).pack(side="left")
        chip = f' · {conf:.0f}%' if conf is not None else ""
        btn = ctk.CTkButton(row, text=f'{icon} #{job["id"]} {name}{chip}', anchor="w",
                            fg_color="transparent", hover_color=theme.CARD_HI,
                            text_color=theme.TEXT,
                            command=lambda j=job["id"]: self._show(j))
        btn.pack(side="left", fill="x", expand=True)

    def _toggle(self, source: str) -> None:
        self.expanded.symmetric_difference_update({source})
        self.refresh()

    def _toggle_one(self, job_id: int, var) -> None:
        (self.selected.add if var.get() else self.selected.discard)(job_id)
        self._update_selection_bar()

    def _toggle_group(self, ids: list[int], var) -> None:
        for i in ids:
            (self.selected.add if var.get() else self.selected.discard)(i)
        self.refresh()

    def _clear_selection(self) -> None:
        self.selected.clear()
        self.refresh()

    def _update_selection_bar(self) -> None:
        n = len(self.selected)
        if n:
            self.sel_label.configure(text=f"{n} job(s) selected")
            self.sel_bar.grid()
        else:
            self.sel_bar.grid_remove()

    def _search(self) -> None:
        self.search_term = self.search_entry.get().strip()
        self.refresh()

    def _clear_search(self) -> None:
        self.search_term = ""
        self.search_entry.delete(0, "end")
        self.refresh()

    # ---------------------------------------------------------------- detail

    def _show(self, job_id: int) -> None:
        """Load one job (DB + preview decode) off-thread, then render it."""
        self.info_label.configure(text=f"Loading job #{job_id}...", text_color=theme.MUTED)
        self.controller.run(
            lambda: self._load_detail(job_id),
            lambda payload: self._post(self._render_detail, payload),
            on_error=lambda exc: self._post(self._render_error, exc))

    @staticmethod
    def _load_detail(job_id: int) -> dict:
        job = service.job_detail(job_id)
        thumb = None
        if job is not None:
            path = service.original_image_path(job)
            if path is not None:
                try:
                    with Image.open(path) as im:
                        im.load()
                        thumb = im.copy()
                    thumb.thumbnail(PREVIEW_MAX)
                except Exception:
                    thumb = None  # corrupt/half-written original — show '(no preview)'
        return {"job": job, "thumb": thumb}

    def _render_detail(self, payload: dict) -> None:
        job = payload["job"]
        if job is None or not self.winfo_exists():
            return
        self.current_job = job
        self._set_actions_enabled(True)
        page = service.page_of(job)
        conf = job["mean_conf"]
        info = (f'Job #{job["id"]}{f" · page {page}" if page else ""}'
                f' · {job["created_at"]} · {job["status"]}'
                f'{f" · confidence {conf}%" if conf is not None else ""}'
                f'\nSource: {job["source_path"]}')
        self.info_label.configure(text=info, text_color=theme.TEXT)
        self.label_entry.delete(0, "end")
        if job.get("label"):
            self.label_entry.insert(0, job["label"])
        self._set_preview(payload["thumb"])

        lines = []
        flagged = [s for s in job["sections"] if s["status"] not in ("ok", "boosted")]
        if flagged:
            lines.append("Sections needing AI Boost: "
                         + ", ".join(f'#{s["idx"]} ({s["status"]})' for s in flagged))
            lines.append("")
        lines.append(job["full_text"] or "(no readable text found)")
        self.detail.delete("1.0", "end")
        self.detail.insert("1.0", "\n".join(lines))

    def _set_preview(self, thumb) -> None:
        if thumb is None:
            self.preview_label.configure(image=None, text="(no image preview)",
                                         text_color=theme.MUTED)
            self._preview_image = None
            return
        self._preview_image = ctk.CTkImage(thumb, size=thumb.size)
        self.preview_label.configure(image=self._preview_image, text="")

    # --------------------------------------------------------------- actions

    def _save_label(self) -> None:
        if not self.current_job:
            return
        service.rename_job(self.current_job["id"], self.label_entry.get())
        self.refresh()

    def _open_folder(self) -> None:
        if self.current_job and not service.open_job_folder(self.current_job["id"]):
            messagebox.showwarning("Jobs", "Could not open the job folder.", parent=self)

    def _copy_text(self) -> None:
        if not self.current_job:
            return
        self.clipboard_clear()
        self.clipboard_append(self.current_job.get("full_text") or "")
        self.info_label.configure(text=self.info_label.cget("text").split("\n")[0]
                                  + "\n📋 Text copied to clipboard.")

    def _export(self, fmt: str) -> None:
        job = self.current_job
        if not job:
            return
        source = job["source_path"].split("#page=")[0]
        name = source.replace("\\", "/").rsplit("/", 1)[-1].rsplit(".", 1)[0]
        dest = filedialog.asksaveasfilename(
            defaultextension=f".{fmt}", initialfile=f"{name}_extract.{fmt}",
            filetypes=[(fmt.upper(), f"*.{fmt}")], parent=self)
        if not dest:
            return
        self.info_label.configure(text=f"Exporting {fmt}...", text_color=theme.MUTED)
        fn = service.export_text if fmt == "txt" else service.export_json
        self.controller.run(
            lambda: fn(source, dest),
            lambda pages: self._post(lambda: messagebox.showinfo(
                "Export", f"Exported {pages} page(s) to:\n{dest}", parent=self)),
            on_error=lambda exc: self._post(self._render_error, exc))

    def _archive(self) -> None:
        job = self.current_job
        if not job:
            return
        if not messagebox.askyesno(
                "Archive job",
                f'Archive job #{job["id"]}?\n\nIt leaves the list and its folder '
                "moves to jobs\\_trash. Nothing is deleted — Empty trash removes "
                "it for good.", parent=self):
            return
        self._run_mutation(lambda: service.archive_job(job["id"]),
                           "🗂 Job archived (recoverable from jobs\\_trash).")

    def _delete_page(self) -> None:
        job = self.current_job
        if not job:
            return
        if not messagebox.askyesno(
                "Delete page", f'Permanently delete job #{job["id"]}?\n'
                "Its folder and data are gone for good.", parent=self):
            return
        self._run_mutation(lambda: service.delete_job(job["id"]),
                           "🗑 Job deleted.")

    def _delete_file(self) -> None:
        job = self.current_job
        if not job:
            return
        source = job["source_path"].split("#page=")[0]
        name = source.replace("\\", "/").rsplit("/", 1)[-1]
        count = service.source_job_count(source)
        if not messagebox.askyesno(
                "Delete whole file",
                f'Permanently delete ALL {count} scanned page(s) of "{name}"?\n'
                "Every page folder and its data are gone for good.", parent=self):
            return
        self._run_mutation(lambda: service.delete_source(source),
                           f"🗑 Deleted all pages of {name}.")

    def _delete_selected(self) -> None:
        ids = sorted(self.selected)
        if not ids or not messagebox.askyesno(
                "Delete selected",
                f"Permanently delete {len(ids)} selected job(s)?\n"
                "Their folders and data are gone for good.", parent=self):
            return
        self._run_mutation(lambda: [service.delete_job(i) for i in ids] and None,
                           f"🗑 Deleted {len(ids)} job(s).", clear_selection=True)

    def _archive_selected(self) -> None:
        ids = sorted(self.selected)
        if not ids or not messagebox.askyesno(
                "Archive selected",
                f"Archive {len(ids)} selected job(s) to jobs\\_trash?\n"
                "Nothing is deleted.", parent=self):
            return
        self._run_mutation(lambda: [service.archive_job(i) for i in ids] and None,
                           f"🗂 Archived {len(ids)} job(s).", clear_selection=True)

    def _empty_trash(self) -> None:
        if not messagebox.askyesno(
                "Empty trash", "Permanently delete ALL archived jobs (jobs\\_trash)?\n"
                "This cannot be undone.", parent=self):
            return
        self._run_mutation(service.empty_trash, "🧹 Trash emptied.")

    def _run_mutation(self, fn, message: str, clear_selection: bool = False) -> None:
        """Run a delete/archive off-thread, then clear the (now stale) detail and
        refresh — never reuse the pre-mutation current_job snapshot."""
        def done(_result):
            self._post(lambda: self._after_mutation(message, clear_selection))
        self.controller.run(fn, done, on_error=lambda exc: self._post(self._render_error, exc))

    def _after_mutation(self, message: str, clear_selection: bool) -> None:
        if clear_selection:
            self.selected.clear()
        self._clear_detail(message)
        self.refresh()

    def _clear_detail(self, message: str) -> None:
        self.current_job = None
        self._set_actions_enabled(False)
        self.info_label.configure(text=message, text_color=theme.TEXT)
        self.preview_label.configure(image=None, text="")
        self._preview_image = None
        self.label_entry.delete(0, "end")
        self.detail.delete("1.0", "end")

    def _overlay(self) -> None:
        """Render the confidence overlay off-thread, then pop it up."""
        job = self.current_job
        if not job:
            return
        self.info_label.configure(text=self.info_label.cget("text").split("\n")[0]
                                  + "\n👁 Rendering overlay...", text_color=theme.MUTED)
        job_id = job["id"]
        self.controller.run(
            lambda: self._build_overlay(job_id),
            lambda payload: self._post(self._show_overlay, job_id, payload),
            on_error=lambda exc: self._post(self._render_error, exc))

    def _build_overlay(self, job_id: int) -> dict:
        out = service.render_overlay(job_id, self.settings.upscale_min_side)
        thumb = None
        if out is not None:
            try:
                with Image.open(out) as im:
                    im.load()
                    thumb = im.copy()
                thumb.thumbnail(OVERLAY_MAX)
            except Exception:
                thumb = None
        return {"path": out, "thumb": thumb}

    def _show_overlay(self, job_id: int, payload: dict) -> None:
        out, thumb = payload["path"], payload["thumb"]
        if out is None or thumb is None:
            messagebox.showwarning("Overlay", "No original image for this job.", parent=self)
            return
        win = ctk.CTkToplevel(self)
        win.title(f'Overlay — job #{job_id} (green ≥75 · yellow ≥60 · red <60)')
        photo = ctk.CTkImage(thumb, size=thumb.size)
        label = ctk.CTkLabel(win, image=photo, text="")
        label.image = photo  # keep alive
        label.pack(padx=theme.S, pady=theme.S)
        win.after(200, win.lift)
        if self.current_job and self.current_job["id"] == job_id:
            self.info_label.configure(
                text=self.info_label.cget("text").split("\n")[0]
                + f"\n👁 Overlay saved: {out.name}", text_color=theme.TEXT)
