"""Shared UI design tokens — one spacing scale, one type scale, one palette so
every tab finally looks like the same app (v0.2.0 redesign).

Before this, each view hand-typed its own paddings (8/12/16/(16,8)...), button
heights and inline hex colours, so nothing lined up. Views now consume these
constants instead. CTkFont helpers must be called after the root window exists
(i.e. inside a view's __init__), which is always the case here.
"""
import customtkinter as ctk

# --- spacing scale (px) ---------------------------------------------------
XS, S, M, L, XL = 4, 8, 12, 16, 24
PAD = M                # default inner padding
GAP = S                # default gap between controls

# --- semantic palette (dark theme) ----------------------------------------
BG = "#1b1c1f"         # window background
CARD = "#26272c"       # raised card / panel
CARD_HI = "#2f3137"    # hover / selected row
BORDER = "#3a3c42"
TEXT = "#e7e8ea"
MUTED = "#9a9ea7"      # secondary text
PRIMARY = "#3d7dff"
PRIMARY_HI = "#5a93ff"
DANGER = "#b23b30"
DANGER_HI = "#d04a3c"
SUCCESS = "#2fa84f"
WARN = "#d8a01d"
ACCENT = "#1f6feb"

# confidence colours (overlay boxes + conf chips) — green/yellow/red bars
CONF_HI, CONF_MID, CONF_LO = "#2fa84f", "#d8a01d", "#d04040"


def conf_color(conf: float | None) -> str:
    """Colour for a confidence value (matches the overlay legend)."""
    if conf is None:
        return MUTED
    if conf >= 75:
        return CONF_HI
    if conf >= 60:
        return CONF_MID
    return CONF_LO


# --- type scale -----------------------------------------------------------
def font_h1() -> ctk.CTkFont:
    return ctk.CTkFont(size=19, weight="bold")


def font_h2() -> ctk.CTkFont:
    return ctk.CTkFont(size=14, weight="bold")


def font_body() -> ctk.CTkFont:
    return ctk.CTkFont(size=13)


def font_caption() -> ctk.CTkFont:
    return ctk.CTkFont(size=11)


def font_mono() -> ctk.CTkFont:
    return ctk.CTkFont(family="Consolas", size=12)


# --- button styles --------------------------------------------------------
def primary_btn(**kw) -> dict:
    return {"fg_color": PRIMARY, "hover_color": PRIMARY_HI, **kw}


def danger_btn(**kw) -> dict:
    return {"fg_color": DANGER, "hover_color": DANGER_HI, **kw}


def ghost_btn(**kw) -> dict:
    """Low-emphasis action — transparent with a hover tint."""
    return {"fg_color": "transparent", "hover_color": CARD_HI,
            "border_width": 1, "border_color": BORDER, "text_color": TEXT, **kw}
