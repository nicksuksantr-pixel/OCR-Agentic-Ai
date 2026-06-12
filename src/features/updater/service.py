"""Silent auto-update via GitHub Releases (Nick's choices, 2026-06-12).

Flow (all offline-safe, never blocks scanning):
  1. On EVERY app start a background thread checks the latest GitHub release
     (v0.1.3: the old once-per-day throttle made quit+reopen miss same-day
     releases — one tiny API call per start is nothing).
  2. Newer tag found → the Setup exe asset is downloaded to %TEMP% and its
     SHA-256 verified against the matching .sha256 asset (built by build.ps1).
  3. The update is STAGED, not forced — it installs the moment the app exits
     (quit from tray or window) via a detached script: wait for exit →
     Setup /VERYSILENT → relaunch the app. No wizard, no questions.
     One UAC consent popup is unavoidable (Program Files install — Windows
     security, not ours to bypass).
Dev runs (not frozen) only report; staging/applying needs a real install.
Disabled until Settings.update_repo is set (e.g. "nick/OCR-Agentic-Ai").
"""
import hashlib
import json
import subprocess
import sys
import tempfile
import threading
import urllib.request
from pathlib import Path

from src.core.config.settings import Settings

ASSET_PREFIX = "OCR-Agentic-Ai_Setup_"   # release asset naming contract (build.ps1)
APP_EXE_NAME = "OCR-Agentic-Ai.exe"


def parse_version(tag: str) -> tuple[int, ...]:
    """'v0.0.9' → (0, 0, 9); tolerant of missing 'v' and junk suffixes."""
    nums = []
    for part in tag.strip().lstrip("vV").split("."):
        digits = "".join(ch for ch in part if ch.isdigit())
        nums.append(int(digits) if digits else 0)
    return tuple(nums or [0])


def fetch_latest_release(repo: str, timeout: float = 10.0) -> dict | None:
    """GET the latest release metadata from the GitHub API (None on any failure)."""
    req = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/releases/latest",
        headers={"User-Agent": "OCR-Agentic-Ai-updater",
                 "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None  # offline / rate-limited / repo missing — never crash the app


def pick_assets(release: dict) -> tuple[dict | None, dict | None]:
    """Find the Setup exe asset and its optional .sha256 sibling."""
    setup = sha = None
    for asset in release.get("assets", []):
        name = asset.get("name", "")
        if name.startswith(ASSET_PREFIX) and name.endswith(".exe"):
            setup = asset
        elif name.startswith(ASSET_PREFIX) and name.endswith(".sha256"):
            sha = asset
    return setup, sha


def download(url: str, dest: Path, timeout: float = 600.0) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "OCR-Agentic-Ai-updater"})
    dest.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(req, timeout=timeout) as resp, open(dest, "wb") as f:
        while chunk := resp.read(1 << 16):
            f.write(chunk)


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def make_apply_script(setup_path: Path, app_exe: Path) -> Path:
    """Write the detached updater script: wait for app exit → silent install → relaunch."""
    bat = Path(tempfile.gettempdir()) / "ocr_agentic_apply_update.bat"
    bat.write_text(
        "@echo off\n"
        ":wait\n"
        f"tasklist /FI \"IMAGENAME eq {APP_EXE_NAME}\" | find /I \"{APP_EXE_NAME}\" >nul "
        "&& (timeout /t 1 /nobreak >nul & goto wait)\n"
        f"\"{setup_path}\" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART\n"
        f"start \"\" \"{app_exe}\"\n"
        "del \"%~f0\"\n",
        encoding="ascii")
    return bat


class AutoUpdater:
    """Owns the staged update state; App calls check_async() at start and
    apply_on_exit() inside its quit path."""

    def __init__(self, settings: Settings, version: str, on_event=lambda msg: None):
        self.settings = settings
        self.version = version
        self.on_event = on_event
        self.staged_setup: Path | None = None  # downloaded+verified, installs on exit

    # --- checking ------------------------------------------------------------

    def check_async(self, manual: bool = False) -> None:
        """Check the release channel in the background. `manual` (the Settings
        "Check now" button) also reports the no-update/disabled outcomes."""
        if not (self.settings.auto_update and self.settings.update_repo.strip()):
            if manual:
                self.on_event("Updater is disabled (Settings → Updates).")
            return
        threading.Thread(target=self._check, args=(manual,), daemon=True,
                         name="update-check").start()

    def _check(self, manual: bool) -> None:
        if self.staged_setup:
            if manual:
                self.on_event("Update already staged — installs when you quit.")
            return
        release = fetch_latest_release(self.settings.update_repo.strip())
        if not release:
            if manual:
                self.on_event("Update check failed — offline or repo unreachable.")
            return
        latest = release.get("tag_name", "")
        if parse_version(latest) <= parse_version(self.version):
            if manual:
                self.on_event(f"Up to date ({self.version} is the latest).")
            return
        setup, sha = pick_assets(release)
        if not setup:
            return
        self.on_event(f"Update {latest} found — downloading in background...")
        if not getattr(sys, "frozen", False):
            self.on_event(f"Update {latest} available (dev run — install skipped).")
            return
        try:
            dest = Path(tempfile.gettempdir()) / "OCR-Agentic-Ai-update" / setup["name"]
            download(setup["browser_download_url"], dest)
            if sha:
                sha_file = dest.with_suffix(dest.suffix + ".sha256")
                download(sha["browser_download_url"], sha_file)
                expected = sha_file.read_text(encoding="utf-8").split()[0].lower()
                if sha256_of(dest) != expected:
                    dest.unlink(missing_ok=True)
                    self.on_event("Update download failed checksum — discarded.")
                    return
            self.staged_setup = dest
            self.on_event(f"Update {latest} ready — installs silently when you quit.")
        except Exception as exc:
            self.on_event(f"Update download failed: {exc}")

    # --- applying ------------------------------------------------------------

    def apply_on_exit(self) -> bool:
        """If an update is staged, launch the detached apply script. Returns True
        when the script was started (caller should proceed to exit)."""
        if not (self.staged_setup and self.staged_setup.exists()):
            return False
        app_exe = Path(sys.executable)
        bat = make_apply_script(self.staged_setup, app_exe)
        subprocess.Popen(
            ["cmd", "/c", str(bat)],
            creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
            close_fds=True)
        return True
