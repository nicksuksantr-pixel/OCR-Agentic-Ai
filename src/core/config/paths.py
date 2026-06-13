"""Central project paths — every file location is defined here, nowhere else.

ONE canonical Shared Store (Nick, v0.2.0 — "dev and installed kept showing me
different data / open-folder was empty"). Before v0.2.0 a dev run used the
project's `data\\` folder while the installed .exe used `%LOCALAPPDATA%`, so the
two diverged — jobs deleted in one came "back" in the other and Open folder
pointed at the wrong tree. Now BOTH dev and installed use the same per-user
location, so there is exactly one library:

- Default (dev AND installed): `%LOCALAPPDATA%\\OCR-Agentic-Ai\\`.
- `OCR_AGENTIC_DATA_DIR` env var overrides it (tests use a throwaway store so
  they never touch the real library; Open-Claw setups can repoint it).

The legacy dev store (`<project>\\data\\`) is migrated once on first run when the
new location is still empty (see `migrate_legacy_store`).
"""
import os
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
LEGACY_DATA_DIR = PROJECT_ROOT / "data"   # pre-v0.2.0 dev store — migrated once

if os.environ.get("OCR_AGENTIC_DATA_DIR"):
    DATA_DIR = Path(os.environ["OCR_AGENTIC_DATA_DIR"])
else:
    # One per-user store for every launch mode — the single source of truth.
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    DATA_DIR = Path(base) / "OCR-Agentic-Ai"

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


def tessdata_dirs() -> list[Path]:
    """Where to look for language models, best first. Includes the project's
    own `data\\tessdata` so a dev run keeps reading `tha` even though the live
    Shared Store moved to %LOCALAPPDATA% (the tha model only ever lived in the
    project tree — winget Tesseract is English-only)."""
    dirs = [TESSDATA_DIR, LEGACY_DATA_DIR / "tessdata"]
    bundled = bundled_tessdata()
    if bundled:
        dirs.append(bundled)
    seen, out = set(), []
    for d in dirs:
        key = str(d).lower()
        if key not in seen:
            seen.add(key)
            out.append(d)
    return out


def ensure_dirs() -> None:
    """Create all runtime data folders if missing (safe to call every start)."""
    for d in (DATA_DIR, INBOX_DIR, INBOX_PROCESSED, INBOX_FAILED, JOBS_DIR, TESSDATA_DIR):
        d.mkdir(parents=True, exist_ok=True)


def migrate_legacy_store() -> str | None:
    """One-time move of the old `<project>\\data` dev store into the canonical
    %LOCALAPPDATA% location — ONLY when the new store has no DB yet, so an
    existing library is never overwritten or merged. Rewrites the absolute
    job_dir paths inside the copied DB so Open folder keeps working.

    Returns a short note when a migration happened, else None.
    """
    if os.environ.get("OCR_AGENTIC_DATA_DIR"):
        return None  # explicit override (tests / Open-Claw) — never auto-migrate
    legacy_db = LEGACY_DATA_DIR / "ocr.db"
    if DB_PATH.exists() or not legacy_db.exists() or LEGACY_DATA_DIR == DATA_DIR:
        return None  # already have a store, or nothing to migrate
    ensure_dirs()
    # Copy the DB and the job folders across.
    shutil.copy2(legacy_db, DB_PATH)
    legacy_jobs = LEGACY_DATA_DIR / "jobs"
    if legacy_jobs.exists():
        for child in legacy_jobs.iterdir():
            target = JOBS_DIR / child.name
            if child.is_dir() and not target.exists():
                shutil.copytree(child, target)
    for extra in ("tessdata", ".env", "boost_usage.json"):
        src = LEGACY_DATA_DIR / extra
        dst = DATA_DIR / extra
        if src.exists() and not dst.exists():
            (shutil.copytree if src.is_dir() else shutil.copy2)(src, dst)
    _rewrite_job_dirs(str(LEGACY_DATA_DIR), str(DATA_DIR))
    return f"migrated legacy store from {LEGACY_DATA_DIR} → {DATA_DIR}"


def _rewrite_job_dirs(old_root: str, new_root: str) -> None:
    """Point every job_dir in the freshly-copied DB at the new location."""
    import sqlite3
    con = sqlite3.connect(DB_PATH)
    try:
        con.execute(
            "UPDATE jobs SET job_dir = REPLACE(job_dir, ?, ?) WHERE job_dir LIKE ?",
            (old_root, new_root, old_root + "%"))
        con.commit()
    finally:
        con.close()
