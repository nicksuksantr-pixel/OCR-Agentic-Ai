"""Headless GUI smoke — build the whole window and ASSERT the redesigned
structure exists and is wired (v0.2.0). The old version only checked the window
built, so a redesign that deleted half the UI would still 'pass' — this is the
regression net for the redesign itself."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import os as _os, tempfile as _tempfile  # noqa: E402 — isolate the test store
_os.environ.setdefault("OCR_AGENTIC_DATA_DIR",
                       str(Path(_tempfile.gettempdir()) / "ocr-agentic-tests"))

sys.stdout.reconfigure(encoding="utf-8")

from src.app.app import App
from src.core.models.ocr import Word
from src.core.services import store


def main() -> None:
    checks: dict[str, bool] = {}
    app = App()
    app.update()  # force one full render of every tab

    # --- tabs present ---
    try:
        present = all(app.tabs.tab(n) is not None
                      for n in ("Scan", "Jobs", "Dashboard", "Settings"))
    except Exception:
        present = False
    checks["four tabs present"] = present

    # --- key widgets exist on each view ---
    checks["scan pick button"] = hasattr(app.scan_view, "pick_btn")
    checks["scan banner refresh"] = hasattr(app.scan_view, "refresh_banners")
    checks["jobs list + detail actions"] = (hasattr(app.jobs_view, "job_list")
                                            and len(app.jobs_view._actions) >= 6)
    checks["settings save + tess path"] = (hasattr(app.settings_view, "tess_entry")
                                           and hasattr(app.settings_view, "save_status"))
    checks["dashboard activity log"] = hasattr(app.dashboard_view, "activity_log")
    checks["bottom status strip"] = hasattr(app, "status_strip")

    # --- detail actions disabled until a job is selected ---
    checks["actions disabled with no selection"] = all(
        b.cget("state") == "disabled" for b in app.jobs_view._actions)

    # --- the shared activity log actually receives a routed message ---
    app.log("TEST", "hello from smoke", "ok")
    app.update()
    log_text = app.dashboard_view.activity_log._box.get("1.0", "end")
    checks["activity log routes messages"] = "hello from smoke" in log_text
    checks["status strip updates"] = "hello from smoke" in app.status_strip.cget("text")

    # --- selecting a job enables the action row (simulate _render_detail) ---
    job_id = store.create_job("smoke_gui_select.png", "", "eng")
    store.add_words(job_id, [Word("X", 90.0, 1, 1, 10, 10)])
    store.finish_job(job_id, "X", 90.0)
    app.jobs_view._render_detail({"job": store.get_job(job_id), "thumb": None})
    app.update()
    checks["actions enabled after select"] = all(
        b.cget("state") == "normal" for b in app.jobs_view._actions)
    store.delete_job(job_id)

    app.destroy()

    failed = [n for n, ok in checks.items() if not ok]
    for n, ok in checks.items():
        print(("✅" if ok else "❌"), n)
    print(f"\nGUI SMOKE: {'FAIL' if failed else 'PASS'}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
