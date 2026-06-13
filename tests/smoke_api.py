"""Headless smoke test for the local API — start the server, hit every endpoint."""
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import os as _os, tempfile as _tempfile  # noqa: E402 — isolate the test store
_os.environ.setdefault("OCR_AGENTIC_DATA_DIR",
                       str(Path(_tempfile.gettempdir()) / "ocr-agentic-tests"))

sys.stdout.reconfigure(encoding="utf-8")

from src.core.config import paths
from src.core.config import settings as settings_mod
from src.core.services import engine, store
from src.features.api.service import ApiServer

TEST_PORT = 18765  # off the default so a running GUI never collides


def call(method: str, route: str, body: dict | None = None, token: str | None = None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-OCR-Token"] = token
    req = urllib.request.Request(
        f"http://127.0.0.1:{TEST_PORT}{route}", method=method,
        data=json.dumps(body).encode() if body else None,
        headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


def main() -> None:
    paths.ensure_dirs()
    settings = settings_mod.load()
    settings.api_port = TEST_PORT
    err = engine.configure(settings)
    if err:
        print("ENGINE ERROR:", err)
        sys.exit(1)

    api = ApiServer(settings, "smoke", on_event=lambda m: print(" ", m))
    err = api.start()
    if err:
        print("API ERROR:", err)
        sys.exit(1)

    token = store.api_token()  # POST routes require it (v0.2.4)

    code, health = call("GET", "/health")
    print("health:", code, health)

    code_intro, intro = call("GET", "/introduce")
    print("introduce:", code_intro, "| role:", intro.get("role"),
          "| db:", intro.get("shared_store", {}).get("db_path", "")[-30:])

    code, jobs = call("GET", "/jobs?limit=3")
    print("jobs:", code, f"{len(jobs)} row(s)")

    job_id = jobs[0]["id"] if jobs else None
    code_detail, detail = call("GET", f"/jobs/{job_id}") if job_id else (0, {})
    code_result, _ = call("GET", f"/jobs/{job_id}/result") if job_id else (0, {})
    code_404, _ = call("GET", "/jobs/999999")
    code_unauth, _ = call("POST", "/boost/run")  # no token → must be 401
    code_bad, _ = call("POST", "/scan", {"path": "no_such_file.png"}, token=token)

    test_img = paths.DATA_DIR / "smoke_test.png"
    code_scan, scan = (call("POST", "/scan", {"path": str(test_img)}, token=token)
                       if test_img.exists() else (0, {}))
    print("scan:", code_scan, {k: scan.get(k) for k in ("job_id", "mean_conf", "queued_sections")})

    # Endpoint check only — clear pending items first so the test NEVER sends
    # real Gemini requests (live sends burned daily quota in earlier runs).
    import sqlite3
    con = sqlite3.connect(paths.DB_PATH)
    con.execute("UPDATE boost_queue SET status = 'answered', "
                "ai_text = '(cleared by smoke_api — never sent)' WHERE status = 'pending'")
    con.commit()
    con.close()
    code_boost, boost = call("POST", "/boost/run", token=token)
    print("boost/run:", code_boost, boost.get("stopped_reason") or boost)

    api.stop()
    checks = {
        "health ok": code == 200 and health.get("status") == "ok",
        "introduce ok": code_intro == 200 and intro.get("role") == "eyes"
                        and "endpoints" in intro.get("interfaces", {}).get("api", {}),
        "jobs list": code == 200,
        "job detail + result": code_detail == 200 and code_result == 200,
        "404 on missing job": code_404 == 404,
        "401 on POST without token": code_unauth == 401,
        "400 on bad scan body": code_bad == 400,
        "scan via API works": code_scan == 200 and scan.get("job_id"),
        "boost/run responds": code_boost == 200,
    }
    print()
    for name, ok in checks.items():
        print(("✅" if ok else "❌"), name)
    sys.exit(0 if all(checks.values()) else 1)


if __name__ == "__main__":
    main()
