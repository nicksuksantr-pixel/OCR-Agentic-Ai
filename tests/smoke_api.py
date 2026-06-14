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

from PIL import Image, ImageDraw, ImageFont

from src.core.config import paths
from src.core.config import settings as settings_mod
from src.core.services import engine, gemini, store
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


def _make_test_image(path: Path) -> None:
    """Self-seed our OWN scannable image so this suite never depends on another
    suite (smoke_pipeline) having seeded the shared store first — it must pass
    standalone on a clean store, in any run order (Lucifer audit)."""
    img = Image.new("L", (600, 160), 255)
    ImageDraw.Draw(img).text((20, 60), "LOCAL API SMOKE VALVE V-12",
                             font=ImageFont.truetype("arial.ttf", 30), fill=0)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)


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

    # Scan our self-seeded image FIRST so a real job exists for the jobs-list /
    # detail / result checks below — independent of any other suite (Lucifer audit).
    test_img = paths.DATA_DIR / "smoke_api_test.png"
    _make_test_image(test_img)
    code_scan, scan = call("POST", "/scan", {"path": str(test_img)}, token=token)
    print("scan:", code_scan, {k: scan.get(k) for k in ("job_id", "mean_conf", "queued_sections")})
    scanned_id = scan.get("job_id")

    code, jobs = call("GET", "/jobs?limit=3")
    print("jobs:", code, f"{len(jobs)} row(s)")

    job_id = scanned_id or (jobs[0]["id"] if jobs else None)
    code_detail, detail = call("GET", f"/jobs/{job_id}") if job_id else (0, {})
    code_result, _ = call("GET", f"/jobs/{job_id}/result") if job_id else (0, {})
    code_404, _ = call("GET", "/jobs/999999")
    code_unauth, _ = call("POST", "/boost/run")  # no token → must be 401
    code_bad, _ = call("POST", "/scan", {"path": "no_such_file.png"}, token=token)

    # Endpoint check only — force NO Gemini key so /boost/run returns at the key
    # check BEFORE the drain and can NEVER send a real request. The old "clear the
    # pending rows" guard is no longer enough: _drain now re-enqueues unclear
    # sections at the start (store.requeue_unclear_sections, v0.3.0), which would
    # re-fill the queue from the section this suite just scanned and hit the REAL
    # API (a dev run reads the real key from the project .env). No-key is
    # bulletproof and still exercises the route → 200. smoke_boost covers the real
    # drain+merge with a faked gemini.boost_section. NEVER let a test send live
    # (bug_v0.0.8 — live sends burned the daily quota; reintroduced by requeue).
    gemini.read_api_key = lambda: None
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
