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


def resolve_job_dir(job: dict) -> Path | None:
    """The job's folder, healed against a stale/foreign stored path.

    The DB keeps an absolute job_dir; after a move (archive) or a migration that
    path can be wrong. Try, in order: the stored path → the canonical
    jobs/job_NNNN → the same basename under jobs/_trash. Returns the first that
    exists on disk, or None. This is why Open folder no longer throws Windows'
    'Location is not available' (v0.2.0)."""
    candidates = []
    if job.get("job_dir"):
        candidates.append(Path(job["job_dir"]))
    candidates.append(paths.JOBS_DIR / f"job_{job['id']:04d}")
    if job.get("job_dir"):
        candidates.append(TRASH_DIR / Path(job["job_dir"]).name)
    candidates.append(TRASH_DIR / f"job_{job['id']:04d}")
    for c in candidates:
        if c.exists():
            return c
    return None


def open_data_folder() -> None:
    """Open the Shared Store root in Explorer."""
    os.startfile(paths.DATA_DIR)  # noqa: S606 — local folder, user-initiated


def open_job_folder(job_id: int) -> bool:
    """Open one job's folder in Explorer, healing a moved/stale path. Falls back
    to the jobs root if the exact folder is truly gone, so the click always
    opens *something* real instead of erroring. Returns False only when even the
    data root can't be opened."""
    job = store.get_job(job_id)
    target = resolve_job_dir(job) if job else None
    if target is None:
        target = paths.JOBS_DIR if paths.JOBS_DIR.exists() else paths.DATA_DIR
    try:
        os.startfile(target)  # noqa: S606
        return True
    except OSError:
        return False


def archive_job(job_id: int) -> str:
    """Hide a job and move its folder to jobs/_trash (recycle bin — never deleted).

    Idempotent (v0.2.0): a job already archived, or whose folder already lives in
    _trash, is left exactly where it is — re-archiving used to re-suffix the
    folder (job_0002 → job_0002_1_1_1) and was the visible face of 'trashed jobs
    coming back'. The trash name is id-qualified so two jobs never collide.
    Returns the folder location for the confirmation message."""
    job = store.get_job(job_id)
    if job is None:
        raise ValueError(f"job {job_id} not found")
    src = Path(job["job_dir"]) if job.get("job_dir") else None
    # Already in trash (by flag or by path) → no move, just ensure the flag.
    if job.get("archived") or (src and TRASH_DIR in src.parents):
        if not job.get("archived"):
            store.set_archived(job_id, str(src))
        return str(src) if src else ""
    TRASH_DIR.mkdir(parents=True, exist_ok=True)
    target = TRASH_DIR / f"job_{job_id:04d}"  # id-qualified — never collides
    real_src = resolve_job_dir(job)
    if real_src and real_src.exists() and real_src != target:
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
        shutil.move(str(real_src), str(target))
    store.set_archived(job_id, str(target))
    return str(target)


def delete_job(job_id: int) -> None:
    """Permanently delete one job: folder gone, all DB rows gone, AND the
    original the inbox watcher parked in inbox/processed (so a deleted scan can
    never be resurrected by a future re-import). User-confirmed."""
    job = store.get_job(job_id)
    if job is None:
        return
    target = resolve_job_dir(job)
    if target is not None:
        shutil.rmtree(target, ignore_errors=True)
    _purge_processed_original(job)
    store.delete_job(job_id)


def _purge_processed_original(job: dict) -> None:
    """Best-effort removal of the source's copy in inbox/processed — delete must
    leave nothing that a later 'reprocess' could turn back into this job."""
    source = job["source_path"].split("#page=")[0]
    name = source.replace("\\", "/").rsplit("/", 1)[-1]
    if not name:
        return
    # Exact basename only — a stem wildcard ("report*.pdf") would also match a
    # DIFFERENT source's clash-renamed copy ("report_1.pdf" the watcher made for a
    # second, unrelated "report.pdf") and delete that other source's processed
    # original. A rare stale leftover is far better than erasing unrelated data (audit P3).
    try:
        target = paths.INBOX_PROCESSED / name
        if target.is_file():
            target.unlink(missing_ok=True)
    except OSError:
        pass


def delete_source(source: str) -> int:
    """Permanently delete every page-job of one Source file; returns the count.
    Queries by source in SQL (no 500-row cap), so files past the newest 500
    jobs are no longer silently left behind as orphans (v0.2.0)."""
    rows = store.jobs_for_source(source)
    for j in rows:
        delete_job(j["id"])
    return len(rows)


def source_job_count(source: str) -> int:
    """How many active jobs belong to one Source file (SQL, no cap)."""
    return len(store.jobs_for_source(source))


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
    job_dir = resolve_job_dir(job)
    if job_dir is None:
        return None
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
        job_dir = resolve_job_dir(job)  # heal a moved/stale folder (e.g. under _trash)
        result_path = (job_dir / "result.json") if job_dir else Path(job["job_dir"]) / "result.json"
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
    """All full job rows of one Source file, page order (SQL, no cap)."""
    return [store.get_job(j["id"]) for j in store.jobs_for_source(source)]


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
    job_dir = resolve_job_dir(job)
    original = original_image_path(job)
    if original is None or job_dir is None:
        return None
    with Image.open(original) as src:  # close the file handle so delete can rmtree later
        img = imaging.preprocess(src, upscale_min_side).convert("RGB")
    # v0.1.5: the scan may have turned the page upright before reading — word
    # boxes live in that rotated space, so the overlay must rotate the same way.
    try:
        meta = json.loads((job_dir / "result.json").read_text(encoding="utf-8"))
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
    out = job_dir / "overlay.png"
    img.save(out)
    return out
