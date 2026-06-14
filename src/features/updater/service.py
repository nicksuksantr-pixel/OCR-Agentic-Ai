"""Silent auto-update via GitHub Releases (Nick's choices, 2026-06-12).

Flow (all offline-safe, never blocks scanning):
  1. On EVERY app start a background thread checks the latest GitHub release
     (v0.1.3: the old once-per-day throttle made quit+reopen miss same-day
     releases — one tiny API call per start is nothing).
  2. Newer tag found → the Setup exe asset is downloaded to %TEMP% and its
     SHA-256 verified against the matching .sha256 asset (built by build.ps1).
  3. The update is STAGED, not forced — it installs the moment the app exits
     (quit from tray or window) via a detached script: wait for exit →
     Setup /SILENT (a VISIBLE progress window, so the user can see it happen and
     does not reopen the old exe mid-install) → relaunch the app. No wizard
     pages, but not invisible. One UAC consent popup is unavoidable (Program
     Files install — Windows security, not ours to bypass).
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

from src.core.config import paths
from src.core.config.settings import Settings

ASSET_PREFIX = "OCR-Agentic-Ai_Setup_"   # release asset naming contract (build.ps1)
APP_EXE_NAME = "OCR-Agentic-Ai.exe"


def parse_version(tag: str) -> tuple[int, int, int]:
    """'v0.0.9' → (0, 0, 9); tolerant of missing 'v' and junk suffixes. ALWAYS a
    fixed 3-tuple so a longer tag can't compare greater on padding alone —
    'v0.1.5.0' vs 'v0.1.5' used to read as newer and re-install the SAME build
    on every quit, looping a UAC prompt (v0.2.0 fix)."""
    nums = []
    for part in tag.strip().lstrip("vV").split("."):
        digits = "".join(ch for ch in part if ch.isdigit())
        nums.append(int(digits) if digits else 0)
    nums = (nums + [0, 0, 0])[:3]
    return (nums[0], nums[1], nums[2])


def is_newer(latest_tag: str, current_tag: str) -> bool:
    """True when `latest_tag` is a strictly newer release than `current_tag` —
    the ONLY update gate (v0.3.0).

    We deliberately do NOT also floor at the last tag handed to the installer
    (the old `applied_update.json`): `apply_on_exit` recorded that tag BEFORE the
    install actually ran, so a failed or UAC-dismissed install left the record
    ABOVE the version that was really running, and the app then reported
    'up to date' forever — permanently stuck on the old build, unable to update
    (Nick, 2026-06-14: installed v0.2.8, record said v0.2.9, every check said
    'v0.2.8 is the latest'). The padding loop that floor once guarded
    ('v0.1.5.0' vs 'v0.1.5') is already handled by parse_version's fixed 3-tuple,
    and an in-session re-download is guarded by `staged_setup`. Comparing against
    the running build alone is sufficient AND self-healing: a failed install just
    re-offers on the next start instead of latching off."""
    return parse_version(latest_tag) > parse_version(current_tag)


def _cleanup_legacy_applied() -> None:
    """Delete the pre-v0.3.0 `applied_update.json` if present. It is no longer
    read (see is_newer); removing it un-sticks any install the old
    write-before-install left poisoned (tag recorded above the version that
    actually ended up installed)."""
    try:
        (paths.DATA_DIR / "applied_update.json").unlink(missing_ok=True)
    except OSError:
        pass


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
    """Write the detached updater script: wait for app exit → VISIBLE install →
    relaunch. /SILENT (not /VERYSILENT) shows a progress window so the user can
    SEE the update run — a fully invisible install left the app gone for a minute
    with no sign of life, so people reopened the old exe mid-install and raced it,
    and never knew when it finished (Nick, v0.3.0). The relaunch starts from the
    install dir so the fresh exe comes up clean; the installer also relaunches as
    a backstop and the single-instance mutex dedups any double launch."""
    bat = Path(tempfile.gettempdir()) / "ocr_agentic_apply_update.bat"
    app_dir = app_exe.parent
    bat.write_text(
        "@echo off\n"
        ":wait\n"
        f"tasklist /FI \"IMAGENAME eq {APP_EXE_NAME}\" | find /I \"{APP_EXE_NAME}\" >nul "
        "&& (timeout /t 1 /nobreak >nul & goto wait)\n"
        f"\"{setup_path}\" /SILENT /SUPPRESSMSGBOXES /NORESTART\n"
        "timeout /t 2 /nobreak >nul\n"
        f"start \"\" /D \"{app_dir}\" \"{app_exe}\"\n"
        "del \"%~f0\"\n",
        encoding="ascii")
    return bat


class AutoUpdater:
    """Owns the staged update state; App calls check_async() at start and
    apply_on_exit() inside its quit path."""

    def __init__(self, settings: Settings, version: str, on_event=lambda msg: None,
                 on_ready=lambda tag: None):
        self.settings = settings
        self.version = version
        self.on_event = on_event
        self.on_ready = on_ready               # fired (with the tag) when an update is staged
        self.staged_setup: Path | None = None  # downloaded+verified, installs on exit
        self.staged_tag: str | None = None     # the tag that setup carries
        self.latest_tag: str | None = None     # newest tag the channel offers
        # UI-readable state: disabled | idle | checking | uptodate | available
        #                  | downloading | ready | error
        self.state: str = "idle"
        _cleanup_legacy_applied()  # drop the poison-prone pre-v0.3.0 record (self-heal)

    # --- checking ------------------------------------------------------------

    def check_async(self, manual: bool = False) -> None:
        """Check the release channel in the background. `manual` (the Settings
        "Check now" button) also reports the no-update/disabled outcomes."""
        if not (self.settings.auto_update and self.settings.update_repo.strip()):
            self.state = "disabled"
            if manual:
                self.on_event("Updater is disabled (Settings → Updates).")
            return
        if self.state == "ready":  # already have one waiting — re-announce, don't re-fetch
            self.on_ready(self.staged_tag)
            return
        self.state = "checking"
        if manual:
            self.on_event("Checking for updates...")
        threading.Thread(target=self._check, args=(manual,), daemon=True,
                         name="update-check").start()

    def _check(self, manual: bool) -> None:
        if self.staged_setup:
            self.state = "ready"
            self.on_ready(self.staged_tag)
            return
        release = fetch_latest_release(self.settings.update_repo.strip())
        if not release:
            self.state = "error"
            self.on_event("Update check failed — offline or repo unreachable.")
            return
        latest = release.get("tag_name", "")
        self.latest_tag = latest
        # Update iff the newest release is strictly newer than the RUNNING build.
        # (No applied-tag floor any more — that is what got installs permanently
        # stuck; see is_newer.)
        if not is_newer(latest, self.version):
            self.state = "uptodate"
            self.on_event(f"Up to date ({self.version} is the latest).")
            return
        setup, sha = pick_assets(release)
        if not setup:
            self.state = "error"
            return
        if not getattr(sys, "frozen", False):
            self.state = "available"
            self.on_event(f"Update {latest} available (dev run — install skipped).")
            return
        self.state = "downloading"
        self.on_event(f"Update {latest} found — downloading...")
        try:
            dest = Path(tempfile.gettempdir()) / "OCR-Agentic-Ai-update" / setup["name"]
            download(setup["browser_download_url"], dest)
            if not sha:
                # No .sha256 sibling on the release → refuse to stage. This binary is
                # later run elevated and silent (/SILENT) on exit, so installing
                # it unverified would trust whatever the release serves. Every real
                # release ships its checksum (build.ps1); a missing one is a pipeline
                # slip or a tampered release — stop and require a manual update (v0.2.3).
                dest.unlink(missing_ok=True)
                self.state = "available"
                self.on_event(f"Update {latest} has no checksum asset — not auto-installing; "
                              "please update manually.")
                return
            sha_file = dest.with_suffix(dest.suffix + ".sha256")
            download(sha["browser_download_url"], sha_file)
            expected = sha_file.read_text(encoding="utf-8").split()[0].lower()
            if sha256_of(dest) != expected:
                dest.unlink(missing_ok=True)
                self.state = "error"
                self.on_event("Update download failed checksum — discarded.")
                return
            self.staged_setup = dest
            self.staged_tag = latest
            self.state = "ready"
            self.on_event(f"Update {latest} is ready to install.")
            self.on_ready(latest)
        except Exception as exc:
            self.state = "error"
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
