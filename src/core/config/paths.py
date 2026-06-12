"""Central project paths — every file location is defined here, nowhere else.

Two layouts (Nick's order, 2026-06-12 — "installed = like a normal program"):
- Dev (running from source): everything under the project's `data\\` folder.
- Installed (.exe, PyInstaller `sys.frozen`): Shared Store in
  `%LOCALAPPDATA%\\OCR-Agentic-Ai\\` — survives updates, never lands in the
  PyInstaller temp dir, standard Windows per-user app-data convention.
- `OCR_AGENTIC_DATA_DIR` env var overrides both (testing / Open-Claw setups).
"""
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]

if os.environ.get("OCR_AGENTIC_DATA_DIR"):
    DATA_DIR = Path(os.environ["OCR_AGENTIC_DATA_DIR"])
elif getattr(sys, "frozen", False):
    DATA_DIR = Path(os.environ["LOCALAPPDATA"]) / "OCR-Agentic-Ai"
else:
    DATA_DIR = PROJECT_ROOT / "data"     # Shared Store root (DB + jobs + inbox)

INBOX_DIR = DATA_DIR / "inbox"            # watched folder — drop a file, it gets scanned
INBOX_PROCESSED = INBOX_DIR / "processed" # originals moved here after a successful auto-scan
INBOX_FAILED = INBOX_DIR / "failed"       # originals moved here when the auto-scan errored
JOBS_DIR = DATA_DIR / "jobs"              # one folder per Job: original + crops + result.json
TESSDATA_DIR = DATA_DIR / "tessdata"      # local language models (eng/tha) — no admin needed
DB_PATH = DATA_DIR / "ocr.db"             # SQLite Shared Store (read by Open-Claw too)
SETTINGS_PATH = DATA_DIR / "settings.json"
ENV_PATH = (DATA_DIR if getattr(sys, "frozen", False) else PROJECT_ROOT) / ".env"  # Gemini key


def asset(name: str) -> Path:
    """Resolve a bundled asset (icons etc.) in both dev and frozen layouts."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)) / "assets" / name
    return PROJECT_ROOT / "assets" / name


def bundled_tesseract() -> Path | None:
    """Installed builds carry their own Tesseract — zero external dependency."""
    if getattr(sys, "frozen", False):
        exe = Path(sys.executable).parent / "tesseract" / "tesseract.exe"
        if exe.exists():
            return exe
    return None


def bundled_tessdata() -> Path | None:
    """Language models shipped inside the install dir (read-only is fine)."""
    if getattr(sys, "frozen", False):
        td = Path(sys.executable).parent / "tesseract" / "tessdata"
        if any(td.glob("*.traineddata")):
            return td
    return None


def ensure_dirs() -> None:
    """Create all runtime data folders if missing (safe to call every start)."""
    for d in (DATA_DIR, INBOX_DIR, INBOX_PROCESSED, INBOX_FAILED, JOBS_DIR, TESSDATA_DIR):
        d.mkdir(parents=True, exist_ok=True)
