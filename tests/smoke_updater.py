"""Updater smoke — pure offline: version math, asset picking, apply-script shape.

No network, no GitHub, no installer runs. The live path is exercised the first
time a real release exists on the configured repo.
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import os as _os, tempfile as _tempfile  # noqa: E402 — isolate the test store
_os.environ.setdefault("OCR_AGENTIC_DATA_DIR",
                       str(Path(_tempfile.gettempdir()) / "ocr-agentic-tests"))

sys.stdout.reconfigure(encoding="utf-8")

from src.core.config.settings import Settings
from src.features.updater import service as upd


def check(ok: bool, label: str) -> bool:
    print(("✅" if ok else "❌"), label)
    return ok


def main() -> None:
    all_ok = check(upd.parse_version("v0.0.9") == (0, 0, 9), "parse_version basic")
    all_ok &= check(upd.parse_version("0.1.0") > upd.parse_version("v0.0.9"),
                    "version compare 0.1.0 > 0.0.9")
    all_ok &= check(upd.parse_version("v0.0.10-beta") == (0, 0, 10), "junk suffix tolerated")

    # is_newer = the ONLY update gate (v0.3.0). It must NOT consult any applied-tag
    # record (that before-install write got installs permanently stuck reporting
    # 'up to date'); a strictly-greater release wins, equal/older does not, and the
    # carry boundary 0.2.9 -> 0.3.0 must read as newer.
    all_ok &= check(upd.is_newer("v0.2.9", "v0.2.8"), "is_newer: newer release detected")
    all_ok &= check(not upd.is_newer("v0.2.8", "v0.2.8"), "is_newer: same version not newer")
    all_ok &= check(not upd.is_newer("v0.2.8", "v0.2.9"), "is_newer: older release not newer")
    all_ok &= check(upd.is_newer("v0.3.0", "v0.2.9"), "is_newer: carry boundary 0.3.0 > 0.2.9")

    release = {"tag_name": "v0.1.0", "assets": [
        {"name": "Source code (zip)", "browser_download_url": "x"},
        {"name": "OCR-Agentic-Ai_Setup_v0.1.0.exe", "browser_download_url": "x"},
        {"name": "OCR-Agentic-Ai_Setup_v0.1.0.exe.sha256", "browser_download_url": "x"},
    ]}
    setup, sha = upd.pick_assets(release)
    all_ok &= check(setup and setup["name"].endswith(".exe"), "setup asset picked")
    all_ok &= check(sha and sha["name"].endswith(".sha256"), "sha256 asset picked")

    # sha256_of matches PowerShell-style sidecar content
    tmp = Path(tempfile.gettempdir()) / "ocr_upd_smoke.bin"
    tmp.write_bytes(b"hello update")
    all_ok &= check(len(upd.sha256_of(tmp)) == 64, "sha256_of returns hex digest")

    bat = upd.make_apply_script(Path(r"C:\T\Setup.exe"), Path(r"C:\P\OCR-Agentic-Ai.exe"))
    text = bat.read_text(encoding="ascii")
    all_ok &= check("/SILENT" in text and "/VERYSILENT" not in text and "tasklist" in text
                    and "start " in text and "OCR-Agentic-Ai.exe" in text,
                    "apply script: wait + VISIBLE install + relaunch")
    bat.unlink()

    # Updater stays inert without a configured repo (no thread, no staging)
    u = upd.AutoUpdater(Settings(update_repo=""), "v0.0.9")
    u.check_async()
    all_ok &= check(u.staged_setup is None, "no repo configured → updater inert")
    all_ok &= check(not u.apply_on_exit(), "apply_on_exit no-op when nothing staged")

    print("\nUPDATER SMOKE:", "PASS" if all_ok else "FAIL")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
