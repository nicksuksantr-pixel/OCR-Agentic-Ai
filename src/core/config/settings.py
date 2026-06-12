"""App settings — JSON file in data/, with safe defaults. No keys stored here (.env holds the Gemini key)."""
import json
from dataclasses import dataclass, asdict, field

from src.core.config import paths

DEFAULT_TESSERACT = r"C:\Program Files\Tesseract-OCR\tesseract.exe"


@dataclass
class Settings:
    """User-adjustable settings persisted to data/settings.json."""
    tesseract_path: str = DEFAULT_TESSERACT
    languages: str = "tha+eng"        # local OCR reads Thai + English (CONTEXT: language policy)
    grid_rows: int = 3                # Sectioned Scan grid (3x3 per Nick's idea)
    grid_cols: int = 3
    overlap_pct: float = 0.10         # section overlap so border words are never cut
    low_conf_threshold: float = 60.0  # below this a section goes to the Boost Queue
    rescue_trigger_conf: float = 75.0 # below this the self-rescue pass runs (quality bar > queue bar)
    upscale_min_side: int = 2000      # preprocess: upscale small images to at least this side
    ai_boost_enabled: bool = False    # Gemini booster — off by default, key lives in .env
    gemini_model: str = "gemini-3.1-flash-lite"  # AI Studio free tier; user may pick a paid model
    boost_daily_cap: int = 300        # soft daily request budget (free tier RPD 500, key may be shared)
    paid_tier: bool = False           # unlocked = no RPM throttle, no daily cap, all models (user accepted billing conditions in Settings)
    watch_inbox: bool = True          # auto-scan files dropped into data\inbox
    api_enabled: bool = True          # localhost REST API for Open-Claw (the Heart)
    api_port: int = 8765              # API listens on 127.0.0.1:<port> — local machine only
    tray_enabled: bool = True         # closing the window hides to tray; watcher+API keep running
    auto_grid: bool = True            # scale the section grid with image size (configured grid = minimum, cap 7x7)
    rescue_enabled: bool = True       # unclear sections retry locally (4x zoom/binarize/sparse/rotate) before the Boost Queue
    auto_update: bool = True          # check GitHub Releases daily; silent install on app exit
    update_repo: str = "nicksuksantr-pixel/OCR-Agentic-Ai"  # GitHub update channel; empty disables

    def save(self) -> None:
        """Write settings to disk as JSON."""
        paths.SETTINGS_PATH.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")


def load() -> Settings:
    """Load settings from disk, falling back to defaults for missing/invalid fields."""
    if paths.SETTINGS_PATH.exists():
        try:
            raw = json.loads(paths.SETTINGS_PATH.read_text(encoding="utf-8"))
            known = {k: v for k, v in raw.items() if k in Settings.__dataclass_fields__}
            return Settings(**known)
        except (json.JSONDecodeError, TypeError):
            pass  # corrupted settings file → defaults (never crash on start)
    return Settings()
