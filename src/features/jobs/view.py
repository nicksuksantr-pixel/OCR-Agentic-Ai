"""Jobs tab UI — history of scans + full text of the selected job. UI only."""
import customtkinter as ctk

from src.features.jobs import service


class JobsView(ctk.CTkFrame):
    """The Jobs tab: refreshable job list (left) + detail viewer (right)."""

    def __init__(self, master):
        super().__init__(master, fg_color="transparent")
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self.refresh_btn = ctk.CTkButton(self, text="↻ Refresh", width=100,
                                         command=self.refresh)
        self.refresh_btn.grid(row=0, column=0, padx=16, pady=(16, 8), sticky="w")
        self.boost_label = ctk.CTkLabel(self, text="", anchor="e")
        self.boost_label.grid(row=0, column=1, padx=16, pady=(16, 8), sticky="e")

        self.job_list = ctk.CTkScrollableFrame(self, width=260)
        self.job_list.grid(row=1, column=0, padx=(16, 8), pady=(0, 16), sticky="nsw")
        self.detail = ctk.CTkTextbox(self, wrap="word")
        self.detail.grid(row=1, column=1, padx=(8, 16), pady=(0, 16), sticky="nsew")

        self.refresh()

    def refresh(self) -> None:
        """Reload the job list and the Boost Queue counter from the Shared Store."""
        for child in self.job_list.winfo_children():
            child.destroy()
        for job in service.recent_jobs():
            icon = {"done": "✅", "error": "❌"}.get(job["status"], "⏳")
            name = job["source_path"].replace("\\", "/").rsplit("/", 1)[-1]
            text = f'{icon} #{job["id"]} {name[:24]}'
            ctk.CTkButton(self.job_list, text=text, anchor="w", fg_color="transparent",
                          command=lambda j=job["id"]: self._show(j)).pack(fill="x", pady=1)
        pending = service.boost_pending()
        self.boost_label.configure(
            text=f"🕓 AI Boost queue: {pending} pending" if pending else "AI Boost queue empty")

    def _show(self, job_id: int) -> None:
        """Render one job's stitched text + section statuses."""
        job = service.job_detail(job_id)
        if job is None:
            return
        lines = [f'Job #{job["id"]} · {job["created_at"]} · {job["status"]}'
                 f' · confidence {job["mean_conf"]}%',
                 f'Source: {job["source_path"]}', ""]
        flagged = [s for s in job["sections"] if s["status"] != "ok"]
        if flagged:
            lines.append("Sections needing AI Boost: "
                         + ", ".join(f'#{s["idx"]} ({s["status"]})' for s in flagged))
            lines.append("")
        lines.append(job["full_text"] or "(no text)")
        self.detail.delete("1.0", "end")
        self.detail.insert("1.0", "\n".join(lines))
