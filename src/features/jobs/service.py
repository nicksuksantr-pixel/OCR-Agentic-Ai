"""Jobs feature logic — queries + file management over the Shared Store for the UI."""
import json
import os
import shutil
from pathlib import Path

from PIL import Image, ImageDraw

from src.core.config import paths
from src.core.services import store
from src.core.utils import imaging

TRASH_DIR = paths.JOBS_DIR / "_trash"  # archive target — moved, never deleted (#6)

# Overlay box colours by word confidence (matches the queue/quality bars).
_CONF_COLORS = ((75.0, "#2fa84f"), (60.0, "#d8a01d"), (0.0, "#d04040"))


def recent_jobs(limit: int = 500) -> list[dict]:
    """Latest jobs for the list view."""
    return store.list_jobs(limit=limit)


def grouped_jobs(limit: int = 500) -> list[dict]:
    """Jobs grouped by Source file — a PDF's pages collapse into one group.

    Returns [{source, name, jobs:[...]}] newest group first; jobs inside a
    group are ordered by page (ascending) when pages exist.
    """
    groups: dict[str, dict] = {}
    for job in store.list_jobs(limit=limit):  # newest first
        source = job["source_path"].split("#page=")[0]
        name = source.replace("\\", "/").rsplit("/", 1)[-1]
        groups.setdefault(source, {"source": source, "name": name, "jobs": []})
        groups[source]["jobs"].append(job)
    for g in groups.values():
        g["jobs"].sort(key=lambda j: page_of(j) or 0)
    return list(groups.values())


def page_of(job: dict) -> int | None:
    """Page number from a 'path#page=N' source, None for single images."""
    _, _, page = job["source_path"].partition("#page=")
    return int(page) if page.isdigit() else None


def search(term: str) -> list[dict]:
    """Jobs whose text, source path or label contains the term."""
    return store.search_jobs(term)


def job_detail(job_id: int) -> dict | None:
    """One job with its sections, for the detail pane."""
    return store.get_job(job_id)


def boost_pending() -> int:
    """Count of sections waiting for AI Boost."""
    return store.pending_boost_count()


def rename_job(job_id: int, label: str) -> None:
    """Set/clear the user label shown in the job list."""
    store.set_label(job_id, label)


def open_data_folder() -> None:
    """Open the Shared Store root in Explorer."""
    os.startfile(paths.DATA_DIR)  # noqa: S606 — local folder, user-initiated


def open_job_folder(job_id: int) -> bool:
    """Open one job's folder (original + crops + result.json) in Explorer."""
    job = store.get_job(job_id)
    if job and Path(job["job_dir"]).exists():
        os.startfile(job["job_dir"])  # noqa: S606
        return True
    return False


def archive_job(job_id: int) -> str:
    """Hide a job and move its folder to jobs/_trash (recycle bin — never deleted).

    Returns the new folder location for the confirmation message."""
    job = store.get_job(job_id)
    if job is None:
        raise ValueError(f"job {job_id} not found")
    TRASH_DIR.mkdir(parents=True, exist_ok=True)
    src = Path(job["job_dir"])
    target = TRASH_DIR / src.name
    n = 1
    while target.exists():
        target = TRASH_DIR / f"{src.name}_{n}"
        n += 1
    if src.exists():
        shutil.move(str(src), str(target))
    store.set_archived(job_id, str(target))
    return str(target)


def delete_job(job_id: int) -> None:
    """Permanently delete one job: folder gone, all DB rows gone (user-confirmed)."""
    job = store.get_job(job_id)
    if job is None:
        return
    shutil.rmtree(job["job_dir"], ignore_errors=True)
    store.delete_job(job_id)


def delete_source(source: str) -> int:
    """Permanently delete every page-job of one Source file; returns the count."""
    rows = [j for j in store.list_jobs(limit=500)
            if j["source_path"].split("#page=")[0] == source]
    for j in rows:
        delete_job(j["id"])
    return len(rows)


def source_job_count(source: str) -> int:
    """How many active jobs belong to one Source file."""
    return sum(1 for j in store.list_jobs(limit=500)
               if j["source_path"].split("#page=")[0] == source)


def empty_trash() -> int:
    """Permanently delete everything that was archived (folders in jobs/_trash
    + their hidden DB rows); returns how many jobs were purged."""
    purged = 0
    for job in store.archived_jobs():
        shutil.rmtree(job["job_dir"], ignore_errors=True)
        store.delete_job(job["id"])
        purged += 1
    if TRASH_DIR.exists():
        shutil.rmtree(TRASH_DIR, ignore_errors=True)  # stray leftovers too
    return purged


def original_image_path(job: dict) -> Path | None:
    """The saved original image inside the job folder (original.*)."""
    job_dir = Path(job["job_dir"])
    for f in sorted(job_dir.glob("original.*")):
        return f
    return None


def export_text(source: str, dest: str) -> int:
    """Write every page of a Source as one .txt (page headers); returns page count."""
    jobs = _source_jobs(source)
    blocks = []
    for job in jobs:
        page = page_of(job)
        header = f"=== Page {page} ===\n" if page else ""
        blocks.append(header + (job.get("full_text") or "(no text)"))
    Path(dest).write_text("\n\n".join(blocks), encoding="utf-8")
    return len(jobs)


def export_json(source: str, dest: str) -> int:
    """Combine every page's result.json of a Source into one .json list."""
    payloads = []
    for job in _source_jobs(source):
        result_path = Path(job["job_dir"]) / "result.json"
        if result_path.exists():
            try:
                payloads.append(json.loads(result_path.read_text(encoding="utf-8")))
                continue
            except json.JSONDecodeError:
                pass
        payloads.append({"job_id": job["id"], "source_path": job["source_path"],
                         "full_text": job.get("full_text"), "error": "result.json missing"})
    Path(dest).write_text(json.dumps(payloads, ensure_ascii=False, indent=1),
                          encoding="utf-8")
    return len(payloads)


def _source_jobs(source: str) -> list[dict]:
    """All full job rows of one Source file, page order."""
    rows = [j for j in store.list_jobs(limit=500)
            if j["source_path"].split("#page=")[0] == source]
    rows.sort(key=lambda j: page_of(j) or 0)
    return [store.get_job(j["id"]) for j in rows]


def render_overlay(job_id: int, upscale_min_side: int) -> Path | None:
    """Draw word boxes (coloured by confidence) over the original image.

    Words were detected on the preprocessed canvas, so the original is run
    through the same deterministic preprocess to line the boxes up. The
    rendered image is saved as overlay.png in the job folder and its path
    returned (None when the original image is missing).
    """
    job = store.get_job(job_id)
    if job is None:
        return None
    original = original_image_path(job)
    if original is None:
        return None
    img = imaging.preprocess(Image.open(original), upscale_min_side).convert("RGB")
    # v0.1.5: the scan may have turned the page upright before reading — word
    # boxes live in that rotated space, so the overlay must rotate the same way.
    try:
        meta = json.loads((Path(job["job_dir"]) / "result.json").read_text(encoding="utf-8"))
        rotation = int(meta.get("page_rotation", 0) or 0)
    except (OSError, json.JSONDecodeError, ValueError):
        rotation = 0
    if rotation:
        img = img.rotate(-rotation, expand=True)
    draw = ImageDraw.Draw(img)
    line = max(2, round(min(img.size) / 800))
    for word in store.job_words(job_id):
        color = next(c for floor, c in _CONF_COLORS if word["conf"] >= floor)
        draw.rectangle((word["x"], word["y"], word["x"] + word["w"], word["y"] + word["h"]),
                       outline=color, width=line)
    out = Path(job["job_dir"]) / "overlay.png"
    img.save(out)
    return out
