"""Reusable UI widgets shared across tabs (v0.2.0 redesign).

- ActivityLog: the timestamped, scrollable, append-only feed that finally lets
  the user SEE what the app is doing. Every background door (scan, inbox watcher,
  local API, updater, AI Boost) writes here instead of all stomping one label.
- Tooltip: hover help for icon-only buttons (CustomTkinter has none built in),
  so a glyph button is never a mystery again.
"""
from datetime import datetime

import customtkinter as ctk

from src.shared.ui import theme

_MAX_LINES = 600  # keep the feed bounded — drop the oldest beyond this


class ActivityLog(ctk.CTkFrame):
    """A titled card holding a read-only, auto-scrolling activity feed."""

    def __init__(self, master, title: str = "📜 Activity log", **kw):
        super().__init__(master, fg_color=theme.CARD, corner_radius=10, **kw)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="we", padx=theme.M, pady=(theme.S, 0))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(header, text=title, font=theme.font_h2(),
                     anchor="w").grid(row=0, column=0, sticky="w")
        ctk.CTkButton(header, text="Clear", width=60, height=24,
                      command=self.clear, **theme.ghost_btn()).grid(row=0, column=1, sticky="e")
        self._box = ctk.CTkTextbox(self, wrap="word", font=theme.font_mono(),
                                   fg_color="transparent", activate_scrollbars=True)
        self._box.grid(row=1, column=0, sticky="nsew", padx=theme.S, pady=(theme.XS, theme.S))
        self._box.configure(state="disabled")
        self._lines = 0

    def append(self, message: str, source: str = "", level: str = "info") -> None:
        """Add one timestamped line. Safe to call from the Tk thread only — App
        marshals background-thread events here via after(0, ...)."""
        if not self.winfo_exists():
            return
        icon = {"info": "•", "ok": "✅", "warn": "⚠", "error": "❌"}.get(level, "•")
        stamp = datetime.now().strftime("%H:%M:%S")
        tag = f"[{source}] " if source else ""
        self._box.configure(state="normal")
        self._box.insert("end", f"{stamp} {icon} {tag}{message}\n")
        self._lines += 1
        if self._lines > _MAX_LINES:  # trim the oldest block so it never grows unbounded
            self._box.delete("1.0", f"{self._lines - _MAX_LINES + 1}.0")
            self._lines = _MAX_LINES
        self._box.see("end")
        self._box.configure(state="disabled")

    def clear(self) -> None:
        self._box.configure(state="normal")
        self._box.delete("1.0", "end")
        self._box.configure(state="disabled")
        self._lines = 0


class Tooltip:
    """Lightweight hover tooltip for any widget (icon buttons especially)."""

    def __init__(self, widget, text: str, delay_ms: int = 450):
        self.widget = widget
        self.text = text
        self.delay_ms = delay_ms
        self._after_id = None
        self._tip = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _schedule(self, _event=None) -> None:
        self._cancel()
        self._after_id = self.widget.after(self.delay_ms, self._show)

    def _show(self) -> None:
        if self._tip is not None or not self.widget.winfo_exists():
            return
        x = self.widget.winfo_rootx() + 12
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        self._tip = tip = ctk.CTkToplevel(self.widget)
        tip.overrideredirect(True)
        tip.attributes("-topmost", True)
        tip.geometry(f"+{x}+{y}")
        ctk.CTkLabel(tip, text=self.text, font=theme.font_caption(),
                     fg_color=theme.CARD_HI, corner_radius=6, text_color=theme.TEXT,
                     padx=8, pady=4).pack()

    def _hide(self, _event=None) -> None:
        self._cancel()
        if self._tip is not None:
            self._tip.destroy()
            self._tip = None

    def _cancel(self) -> None:
        if self._after_id is not None:
            try:
                self.widget.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None


def add_tooltip(widget, text: str) -> Tooltip:
    """Attach a hover tooltip; returns it (keep a ref so it isn't GC'd)."""
    return Tooltip(widget, text)


# --- themed modal dialogs (v0.2.2) ----------------------------------------
# Native tkinter messageboxes look nothing like the app (white system chrome on
# a dark UI). These build a small CTk modal in the app's own theme. The toplevel
# is built separately from the blocking wait so a headless test can construct +
# inspect + destroy it without hanging on user input.

_ICON = {"info": ("ℹ", theme.PRIMARY), "warn": ("⚠", theme.WARN),
         "error": ("❌", theme.DANGER), "question": ("❓", theme.PRIMARY)}


def build_dialog(parent, title: str, message: str, buttons: list[tuple],
                 kind: str = "info"):
    """Construct (but do not wait on) a themed modal. `buttons` is a list of
    (label, value, style) where style is 'primary' | 'danger' | 'ghost'.
    Returns (toplevel, result_holder, button_widgets); result_holder['value']
    holds the chosen value once a button is pressed."""
    top = ctk.CTkToplevel(parent)
    top.title(title)
    top.transient(parent)
    top.resizable(False, False)
    top.configure(fg_color=theme.BG)
    result = {"value": None}

    body = ctk.CTkFrame(top, fg_color=theme.BG)
    body.pack(fill="both", expand=True, padx=theme.L, pady=theme.L)
    glyph, color = _ICON.get(kind, _ICON["info"])
    head = ctk.CTkFrame(body, fg_color="transparent")
    head.pack(fill="x", pady=(0, theme.S))
    ctk.CTkLabel(head, text=glyph, font=theme.font_h1(), text_color=color).pack(side="left", padx=(0, theme.S))
    ctk.CTkLabel(head, text=title, font=theme.font_h2(), anchor="w").pack(side="left")
    ctk.CTkLabel(body, text=message, font=theme.font_body(), justify="left",
                 wraplength=400, anchor="w").pack(fill="x", pady=(0, theme.M))
    row = ctk.CTkFrame(body, fg_color="transparent")
    row.pack(fill="x")

    def choose(value):
        result["value"] = value
        try:
            top.grab_release()
        except Exception:
            pass
        top.destroy()

    styles = {"primary": theme.primary_btn, "danger": theme.danger_btn}
    widgets = []
    for label, value, style in buttons:  # first button shows rightmost (default action)
        kw = styles.get(style, theme.ghost_btn)()
        b = ctk.CTkButton(row, text=label, width=96, command=lambda v=value: choose(v), **kw)
        b.pack(side="right", padx=theme.XS)
        widgets.append(b)
    top.protocol("WM_DELETE_WINDOW", lambda: choose(None))
    top._choose = choose  # exposed for tests
    return top, result, widgets


def _run_dialog(parent, title, message, buttons, kind="info"):
    top, result, _ = build_dialog(parent, title, message, buttons, kind)
    top.update_idletasks()
    # centre on the parent window
    try:
        px, py = parent.winfo_rootx(), parent.winfo_rooty()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        w, h = top.winfo_reqwidth(), top.winfo_reqheight()
        top.geometry(f"+{px + max((pw - w) // 2, 0)}+{py + max((ph - h) // 3, 0)}")
    except Exception:
        pass
    top.after(80, lambda: top.winfo_exists() and top.grab_set())  # modal once viewable
    parent.wait_window(top)
    return result["value"]


def ask_yesno(parent, title: str, message: str, kind: str = "question") -> bool:
    return bool(_run_dialog(parent, title, message,
                            [("Yes", True, "primary"), ("No", False, "ghost")], kind))


def show_info(parent, title: str, message: str) -> None:
    _run_dialog(parent, title, message, [("OK", True, "primary")], "info")


def show_warning(parent, title: str, message: str) -> None:
    _run_dialog(parent, title, message, [("OK", True, "primary")], "warn")
