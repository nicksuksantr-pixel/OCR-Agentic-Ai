"""Headless smoke test for the AI Boost sender — offline, Gemini faked.

Seeds one real job with a queued section, monkeypatches gemini.boost_section,
drains the queue and verifies every merge step (DB rows, full_text, result.json).
Pass --live to send ONE real request to Gemini instead (needs .env key + internet).
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import os as _os, tempfile as _tempfile  # noqa: E402 — isolate the test store
_os.environ.setdefault("OCR_AGENTIC_DATA_DIR",
                       str(Path(_tempfile.gettempdir()) / "ocr-agentic-tests"))

sys.stdout.reconfigure(encoding="utf-8")

from PIL import Image, ImageDraw, ImageFont

from src.core.config import paths
from src.core.config import settings as settings_mod
from src.core.services import gemini, store
from src.features.boost import service as boost_service

FAKE_ANSWER = "Breaker CB-101 rating 250A (diode)"


def seed_job() -> tuple[int, dict]:
    """Create a minimal job + queued section directly in the Shared Store."""
    paths.ensure_dirs()
    job_dir = paths.JOBS_DIR / "job_smoke_boost"
    job_dir.mkdir(exist_ok=True)

    img = Image.new("L", (400, 120), 255)
    d = ImageDraw.Draw(img)
    d.text((10, 40), "Breaker CB-101 rating 250A", font=ImageFont.truetype("arial.ttf", 22), fill=0)
    crop_path = job_dir / "section_00.png"
    img.save(crop_path)

    job_id = store.create_job("smoke_boost_source.png", str(job_dir), "tha+eng")
    store.finish_job(job_id, "MAIN TEXT FROM LOCAL PASS", 88.0)
    section_id = store.add_section(job_id, 0, [0, 0, 400, 120], str(crop_path), 31.0, "low_conf")
    store.queue_boost(job_id, section_id, str(crop_path), "Brxxker CB-1O1 ratxng 25OA")

    (job_dir / "result.json").write_text(json.dumps(
        {"job_id": job_id, "full_text": "MAIN TEXT FROM LOCAL PASS"}), encoding="utf-8")
    return job_id, {"section_id": section_id, "job_dir": str(job_dir)}


def seed_unclear_section() -> tuple[int, int]:
    """A job with an unclear section that has a crop but was NEVER queued —
    simulates scanning while AI Boost was OFF / before a key was set (audit P1)."""
    job_dir = paths.JOBS_DIR / "job_smoke_requeue"
    job_dir.mkdir(exist_ok=True)
    crop = job_dir / "section_00.png"
    Image.new("L", (300, 100), 255).save(crop)
    jid = store.create_job("smoke_requeue_source.png", str(job_dir), "eng")
    store.finish_job(jid, "x", 50.0)
    sid = store.add_section(jid, 0, [0, 0, 300, 100], str(crop), 31.0, "low_conf")
    return jid, sid


def main() -> None:
    live = "--live" in sys.argv
    job_id, seeded = seed_job()
    settings = settings_mod.load()
    settings.ai_boost_enabled = True
    settings.paid_tier = False  # exercise the free-tier path (model lock + cap)

    # --- audit P1: a section scanned while Boost was OFF (crop on disk, status
    # unclear, never enqueued) must become boostable LATER without a re-scan ---
    rq_jid, rq_sid = seed_unclear_section()
    store.requeue_unclear_sections()
    rq_status = next(s for s in store.get_job(rq_jid)["sections"]
                     if s["id"] == rq_sid)["status"]
    rq_before = len([i for i in store.pending_boost_items(1000) if i["job_id"] == rq_jid])
    store.requeue_unclear_sections()  # 2nd call must NOT create a duplicate row
    rq_after = len([i for i in store.pending_boost_items(1000) if i["job_id"] == rq_jid])

    # Isolation: drain ONLY the seeded item — never touch real pending queue rows
    # (v0.1.1 lesson: this test used to fake-answer the whole dev queue).
    real_pending = store.pending_boost_items
    store.pending_boost_items = (
        lambda limit=100: [i for i in real_pending(limit) if i["job_id"] == job_id])
    boost_service.store.pending_boost_items = store.pending_boost_items

    models_used: list[str] = []
    if not live:
        settings.gemini_model = "gemini-2.5-pro"  # must be ignored while locked to free
        gemini.boost_section = (
            lambda crop, local, model: (models_used.append(model), FAKE_ANSWER)[1])
        if not gemini.read_api_key():
            gemini.read_api_key = lambda: "fake-key-for-offline-test"

    summary = boost_service.send_pending(settings, on_progress=lambda m: print(" ", m))
    print(f"\nsummary: sent={summary.sent} answered={summary.answered} "
          f"failed={summary.failed} stopped='{summary.stopped_reason}'")

    job = store.get_job(job_id)
    section = next(s for s in job["sections"] if s["id"] == seeded["section_id"])
    result_json = json.loads((Path(seeded["job_dir"]) / "result.json").read_text(encoding="utf-8"))

    checks = {
        "queue answered": summary.answered >= 1,
        "section status boosted": section["status"] == "boosted",
        "full_text got AI Boost block": "[AI Boost]" in (job["full_text"] or ""),
        "result.json got ai_boosts": bool(result_json.get("ai_boosts")),
        "requeue enqueues an OFF-scanned unclear section": rq_status == "queued",
        "requeue is idempotent (no duplicate row)": rq_before == 1 and rq_after == 1,
    }
    if not live:
        checks["ai_text matches fake"] = FAKE_ANSWER in (job["full_text"] or "")
        checks["free tier locked to free model"] = (
            models_used == [boost_service.FREE_MODEL])
    else:
        print("live AI answer:", result_json.get("ai_boosts", [{}])[-1].get("ai_text"))

    print()
    failed = [name for name, ok in checks.items() if not ok]
    for name, ok in checks.items():
        print(("✅" if ok else "❌"), name)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
