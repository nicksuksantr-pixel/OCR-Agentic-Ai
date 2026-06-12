"""Headless smoke test for v0.1.2 data-management features.

Covers: label set/search, grouping, archive (folder → jobs/_trash, hidden from
lists), stats, job_words + overlay render, export txt/json, ScanControl
pause/cancel semantics. Touches ONLY rows/folders it creates (bug_v0.1.1 lesson).
"""
import json
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

from PIL import Image

from src.core.config import paths
from src.core.models.ocr import Word
from src.core.services import store
from src.features.jobs import service as jobs_service
from src.features.scan.service import ScanCancelled, ScanControl

MARKER = "SMOKE-MANAGE-UNIQUE-TOKEN"


def seed_job(page: int) -> int:
    """One fake done job pretending to be a page of smoke_manage.pdf."""
    paths.ensure_dirs()
    job_dir = paths.JOBS_DIR / f"job_smoke_manage_p{page}"
    job_dir.mkdir(exist_ok=True)
    Image.new("L", (300, 200), 255).save(job_dir / "original.png")
    job_id = store.create_job(f"smoke_manage.pdf#page={page}", str(job_dir), "tha+eng")
    store.add_words(job_id, [Word(MARKER, 90.0, 10, 10, 100, 20),
                             Word("dim", 50.0, 10, 50, 60, 20)])
    store.finish_job(job_id, f"{MARKER} page {page} text", 80.0)
    (job_dir / "result.json").write_text(
        json.dumps({"job_id": job_id, "page": page, "pages": 2,
                    "full_text": f"{MARKER} page {page} text"}), encoding="utf-8")
    return job_id


def main() -> None:
    checks: dict[str, bool] = {}
    # Idempotency: archive leftovers from previous runs of THIS test only,
    # so grouping/export counts stay exact.
    for old in store.search_jobs("smoke_manage.pdf"):
        store.set_archived(old["id"], str(jobs_service.TRASH_DIR / "smoke_manage_old"))
    id1, id2 = seed_job(1), seed_job(2)

    # --- label + search ---
    jobs_service.rename_job(id1, "breaker list")
    found = jobs_service.search(MARKER)
    checks["search finds seeded text"] = {id1, id2} <= {j["id"] for j in found}
    checks["search finds label"] = id1 in {j["id"] for j in jobs_service.search("breaker list")}
    checks["label stored"] = next(j for j in found if j["id"] == id1)["label"] == "breaker list"

    # --- grouping ---
    group = next((g for g in jobs_service.grouped_jobs()
                  if g["source"] == "smoke_manage.pdf"), None)
    checks["grouped by source"] = group is not None and len(group["jobs"]) == 2
    checks["group page order"] = (group is not None and
                                  [jobs_service.page_of(j) for j in group["jobs"]] == [1, 2])

    # --- stats ---
    s = store.stats()
    checks["stats keys"] = all(k in s for k in
                               ("total", "done", "error", "processing",
                                "avg_conf", "boost_pending", "boost_answered"))

    # --- overlay ---
    overlay = jobs_service.render_overlay(id1, upscale_min_side=300)
    checks["overlay rendered"] = overlay is not None and overlay.exists()

    # --- export ---
    txt_dest = paths.DATA_DIR / "smoke_manage_export.txt"
    json_dest = paths.DATA_DIR / "smoke_manage_export.json"
    n_txt = jobs_service.export_text("smoke_manage.pdf", str(txt_dest))
    n_json = jobs_service.export_json("smoke_manage.pdf", str(json_dest))
    txt = txt_dest.read_text(encoding="utf-8")
    checks["export txt all pages"] = n_txt == 2 and "=== Page 1 ===" in txt and "page 2 text" in txt
    payloads = json.loads(json_dest.read_text(encoding="utf-8"))
    checks["export json payloads"] = n_json == 2 and payloads[0]["page"] == 1

    # --- archive (move to _trash, hidden, never deleted) ---
    new_dir = jobs_service.archive_job(id2)
    checks["archive moved folder"] = (Path(new_dir).exists()
                                      and "_trash" in new_dir
                                      and (Path(new_dir) / "original.png").exists())
    checks["archived hidden from list"] = id2 not in {j["id"] for j in store.list_jobs(500)}
    checks["archived hidden from search"] = id2 not in {j["id"] for j in jobs_service.search(MARKER)}

    # --- permanent delete (v0.1.4) ---
    del_id = seed_job(3)
    del_dir = Path(store.get_job(del_id)["job_dir"])
    jobs_service.delete_job(del_id)
    checks["delete removes DB row"] = store.get_job(del_id) is None
    checks["delete removes folder"] = not del_dir.exists()

    # --- empty trash (v0.1.4) — purges the job archived above ---
    purged = jobs_service.empty_trash()
    checks["empty trash purges archived"] = purged >= 1 and store.get_job(id2) is None
    checks["trash folder gone"] = not jobs_service.TRASH_DIR.exists()

    # --- content bbox (v0.1.4) ---
    from PIL import ImageDraw
    from src.core.utils import imaging
    page = Image.new("L", (1000, 800), 255)
    ImageDraw.Draw(page).rectangle((300, 200, 700, 600), outline=0, width=3)
    bx0, by0, bx1, by1 = imaging.content_bbox(page)
    checks["content bbox finds ink"] = (bx0 <= 300 and by0 <= 200
                                        and bx1 >= 700 and by1 >= 600
                                        and bx0 >= 280 and by1 <= 620)
    blank_page = Image.new("L", (400, 300), 255)
    checks["content bbox blank page = full"] = imaging.content_bbox(blank_page) == (0, 0, 400, 300)

    # --- ScanControl ---
    control = ScanControl()
    control.pause()
    woke = []
    t = threading.Thread(target=lambda: (control.checkpoint(), woke.append(True)))
    t.start()
    time.sleep(0.5)
    checks["pause blocks checkpoint"] = not woke
    control.resume()
    t.join(timeout=2)
    checks["resume releases checkpoint"] = bool(woke)
    control.cancel()
    try:
        control.checkpoint()
        checks["cancel raises"] = False
    except ScanCancelled:
        checks["cancel raises"] = True

    print()
    failed = [name for name, ok in checks.items() if not ok]
    for name, ok in checks.items():
        print(("✅" if ok else "❌"), name)
    print(f"\nMANAGE SMOKE: {'FAIL' if failed else 'PASS'}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
