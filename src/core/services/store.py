"""Shared Store — SQLite database both this app and Open-Claw (the Heart) read.

Schema: jobs (one per Source) · sections (Sectioned Scan tiles) · words (merged
final words with position+confidence) · boost_queue (unclear sections waiting
for AI when online) · meta (store identity, additive v0.2.0). All labels/fields
English per CONTEXT language policy.

Concurrency (v0.2.0): the GUI thread, the scan worker, the inbox watcher and the
ThreadingHTTPServer API all open this DB. WAL + a busy timeout let them read and
write at once without "database is locked", and the one-time additive migration
runs under a lock so two threads never ALTER the same table at the same moment.
"""
import json
import sqlite3
import threading
import uuid
from datetime import datetime

from src.core.config import paths

SCHEMA_VERSION = 2  # bump only on an additive schema change (Open-Claw contract)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at  TEXT NOT NULL,
    source_path TEXT NOT NULL,
    job_dir     TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'processing',  -- processing | done | error
    languages   TEXT NOT NULL,
    full_text   TEXT,
    mean_conf   REAL,
    error       TEXT,
    label       TEXT,                                -- v0.1.2 additive: user-given name/tag
    archived    INTEGER NOT NULL DEFAULT 0           -- v0.1.2 additive: 1 = hidden, folder in jobs/_trash
);
CREATE TABLE IF NOT EXISTS sections (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id     INTEGER NOT NULL REFERENCES jobs(id),
    idx        INTEGER NOT NULL,                      -- 0..n-1 in grid order
    bbox       TEXT NOT NULL,                         -- [x, y, w, h] on the full image
    crop_path  TEXT,                                  -- saved crop (kept while unresolved)
    mean_conf  REAL,
    status     TEXT NOT NULL DEFAULT 'ok'             -- ok | low_conf | queued | boosted | unreadable
);
CREATE TABLE IF NOT EXISTS words (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id  INTEGER NOT NULL REFERENCES jobs(id),
    text    TEXT NOT NULL,
    conf    REAL NOT NULL,
    x INTEGER, y INTEGER, w INTEGER, h INTEGER
);
CREATE TABLE IF NOT EXISTS boost_queue (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id      INTEGER NOT NULL REFERENCES jobs(id),
    section_id  INTEGER NOT NULL REFERENCES sections(id),
    crop_path   TEXT NOT NULL,
    local_text  TEXT,
    status      TEXT NOT NULL DEFAULT 'pending',      -- pending | sent | answered | failed
    created_at  TEXT NOT NULL,
    answered_at TEXT,
    ai_text     TEXT
);
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,                           -- store identity (v0.2.0 additive)
    value TEXT
);
"""


_migrated = False
_migrate_lock = threading.Lock()


def _connect() -> sqlite3.Connection:
    """Open the Shared Store DB (created on first use), rows as dicts.

    WAL + a 30 s busy timeout make concurrent reads/writes safe across the GUI,
    scan, watcher and API threads. The additive migration runs exactly once,
    guarded by a lock so two threads never race the same ALTER."""
    global _migrated
    paths.DB_PATH.parent.mkdir(parents=True, exist_ok=True)  # store is self-sufficient
    con = sqlite3.connect(paths.DB_PATH, timeout=30.0)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA busy_timeout=30000")
    if not _migrated:
        with _migrate_lock:
            if not _migrated:
                con.executescript(_SCHEMA)
                try:
                    con.execute("PRAGMA journal_mode=WAL")
                except sqlite3.Error:
                    pass  # WAL needs a real file; :memory:/odd FS → default journal
                cols = {r[1] for r in con.execute("PRAGMA table_info(jobs)")}
                if "label" not in cols:  # v0.1.2 additive columns for older DBs
                    con.execute("ALTER TABLE jobs ADD COLUMN label TEXT")
                if "archived" not in cols:
                    con.execute("ALTER TABLE jobs ADD COLUMN archived INTEGER NOT NULL DEFAULT 0")
                _stamp_identity(con)
                con.commit()
                _migrated = True
    return con


def _stamp_identity(con: sqlite3.Connection) -> None:
    """Record a stable store uuid + schema version once (additive meta table).
    Lets a future Open-Claw / a future build detect which store it opened
    instead of silently presenting a divergent DB as current."""
    have = {r["key"] for r in con.execute("SELECT key FROM meta")}
    if "store_uuid" not in have:
        con.execute("INSERT INTO meta (key, value) VALUES ('store_uuid', ?)",
                    (uuid.uuid4().hex,))
    con.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('schema_version', ?)",
                (str(SCHEMA_VERSION),))


def set_meta(key: str, value: str) -> None:
    """Write one meta value (e.g. last_app_version on each start)."""
    with _connect() as con:
        con.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, value))


def get_meta(key: str) -> str | None:
    """Read one meta value (None when unset)."""
    with _connect() as con:
        row = con.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row["value"] if row else None


def create_job(source_path: str, job_dir: str, languages: str) -> int:
    """Insert a new Job row and return its id.

    job_dir may be '' at first: v0.2.0 names the folder from this returned id
    (job_<id:04d>) so the on-disk folder and the DB id never diverge, then calls
    update_job_dir(). That ends the old glob-based numbering that produced reused
    names like job_0002 → job_0002_1_1_1 after archive/delete."""
    with _connect() as con:
        cur = con.execute(
            "INSERT INTO jobs (created_at, source_path, job_dir, languages) VALUES (?,?,?,?)",
            (datetime.now().isoformat(timespec="seconds"), source_path, job_dir, languages),
        )
        return cur.lastrowid


def update_job_dir(job_id: int, job_dir: str) -> None:
    """Set a job's folder path (after it is named from the DB id)."""
    with _connect() as con:
        con.execute("UPDATE jobs SET job_dir=? WHERE id=?", (job_dir, job_id))


def jobs_for_source(source: str, include_archived: bool = False) -> list[dict]:
    """Every page-job of one Source file, page order — queried in SQL with NO
    arbitrary limit (the old code scanned list_jobs(500), so files past the
    newest 500 jobs silently escaped delete/export). Matches both the bare
    source (single image) and source#page=N (PDF pages)."""
    clause = "" if include_archived else " AND archived=0"
    with _connect() as con:
        rows = con.execute(
            "SELECT id, created_at, source_path, status, mean_conf, label, job_dir "
            f"FROM jobs WHERE (source_path = ? OR source_path LIKE ?){clause} "
            "ORDER BY id",
            (source, source + "#page=%")).fetchall()
    out = [dict(r) for r in rows]
    out.sort(key=lambda j: _page_num(j["source_path"]))
    return out


def jobs_for_exact_source(source_path: str) -> list[dict]:
    """Jobs whose source_path matches EXACTLY (one image, or one PDF page) —
    used on resume to clear a previous error/processing attempt for that page
    before re-scanning it, so resume never piles up duplicates."""
    with _connect() as con:
        rows = con.execute(
            "SELECT id, status, job_dir FROM jobs WHERE source_path=? AND archived=0",
            (source_path,)).fetchall()
        return [dict(r) for r in rows]


def _page_num(source_path: str) -> int:
    _, _, page = source_path.partition("#page=")
    return int(page) if page.isdigit() else 0


def finish_job(job_id: int, full_text: str, mean_conf: float) -> None:
    """Mark a Job done with its stitched text and overall confidence."""
    with _connect() as con:
        con.execute("UPDATE jobs SET status='done', full_text=?, mean_conf=? WHERE id=?",
                    (full_text, mean_conf, job_id))


def fail_job(job_id: int, error: str) -> None:
    """Mark a Job as errored, keeping the reason."""
    with _connect() as con:
        con.execute("UPDATE jobs SET status='error', error=? WHERE id=?", (error, job_id))


def add_section(job_id: int, idx: int, bbox: list, crop_path: str | None,
                mean_conf: float | None, status: str) -> int:
    """Insert one Sectioned-Scan tile result and return its id."""
    with _connect() as con:
        cur = con.execute(
            "INSERT INTO sections (job_id, idx, bbox, crop_path, mean_conf, status) VALUES (?,?,?,?,?,?)",
            (job_id, idx, json.dumps(bbox), crop_path, mean_conf, status),
        )
        return cur.lastrowid


def add_words(job_id: int, words: list) -> None:
    """Bulk-insert the merged final words for a Job."""
    with _connect() as con:
        con.executemany(
            "INSERT INTO words (job_id, text, conf, x, y, w, h) VALUES (?,?,?,?,?,?,?)",
            [(job_id, w.text, w.conf, w.x, w.y, w.w, w.h) for w in words],
        )


def queue_boost(job_id: int, section_id: int, crop_path: str, local_text: str) -> None:
    """Put an unclear section into the Boost Queue (sent to AI when online)."""
    with _connect() as con:
        con.execute(
            "INSERT INTO boost_queue (job_id, section_id, crop_path, local_text, created_at) VALUES (?,?,?,?,?)",
            (job_id, section_id, crop_path, local_text,
             datetime.now().isoformat(timespec="seconds")),
        )
        con.execute("UPDATE sections SET status='queued' WHERE id=?", (section_id,))


def list_jobs(limit: int = 50) -> list[dict]:
    """Latest non-archived jobs for the UI list, newest first."""
    with _connect() as con:
        rows = con.execute(
            "SELECT id, created_at, source_path, status, mean_conf, label "
            "FROM jobs WHERE archived=0 ORDER BY id DESC LIMIT ?",
            (limit,)).fetchall()
        return [dict(r) for r in rows]


def search_jobs(term: str, limit: int = 200) -> list[dict]:
    """Find non-archived jobs whose text, source or label contains `term`."""
    like = f"%{term}%"
    with _connect() as con:
        rows = con.execute(
            "SELECT id, created_at, source_path, status, mean_conf, label "
            "FROM jobs WHERE archived=0 AND "
            "(full_text LIKE ? OR source_path LIKE ? OR label LIKE ?) "
            "ORDER BY id DESC LIMIT ?",
            (like, like, like, limit)).fetchall()
        return [dict(r) for r in rows]


def set_label(job_id: int, label: str) -> None:
    """User-given name/tag for a job (empty clears it)."""
    with _connect() as con:
        con.execute("UPDATE jobs SET label=? WHERE id=?",
                    (label.strip() or None, job_id))


def set_archived(job_id: int, new_job_dir: str) -> None:
    """Hide a job from all listings; its folder has been moved to jobs/_trash."""
    with _connect() as con:
        con.execute("UPDATE jobs SET archived=1, job_dir=? WHERE id=?",
                    (new_job_dir, job_id))


def delete_job(job_id: int) -> None:
    """Permanently remove one job and ALL its rows (user-confirmed delete)."""
    with _connect() as con:
        con.execute("DELETE FROM boost_queue WHERE job_id=?", (job_id,))
        con.execute("DELETE FROM words WHERE job_id=?", (job_id,))
        con.execute("DELETE FROM sections WHERE job_id=?", (job_id,))
        con.execute("DELETE FROM jobs WHERE id=?", (job_id,))


def archived_jobs() -> list[dict]:
    """Jobs sitting in the trash (archived=1) — for Empty-trash."""
    with _connect() as con:
        rows = con.execute(
            "SELECT id, job_dir FROM jobs WHERE archived=1").fetchall()
        return [dict(r) for r in rows]


def done_pages(source_path: str) -> set[int]:
    """Page numbers of a PDF Source already accounted for — lets an interrupted
    batch resume instead of starting over. Counts both finished pages AND pages
    the user archived (archive = 'I already have this page', recycle-bin model):
    archiving a few pages must NOT force a 4-min/page re-scan of them (v0.2.0)."""
    with _connect() as con:
        rows = con.execute(
            "SELECT source_path FROM jobs WHERE status='done' "
            "AND source_path LIKE ?", (source_path + "#page=%",)).fetchall()
    pages = set()
    for r in rows:
        _, _, page = r["source_path"].partition("#page=")
        if page.isdigit():
            pages.add(int(page))
    return pages


def fail_orphans() -> int:
    """App start: any job still 'processing' was cut off by a previous exit —
    mark it errored so it stops looking alive. Returns how many were closed.

    Safe to mark all of them: the session-global single-instance mutex (main.py)
    means no other instance — dev or installed — is scanning into the same store
    when this runs at startup."""
    with _connect() as con:
        return con.execute(
            "UPDATE jobs SET status='error', "
            "error='interrupted — app closed during the scan' "
            "WHERE status='processing'").rowcount


def job_words(job_id: int) -> list[dict]:
    """All merged words of a job with positions — for the overlay viewer."""
    with _connect() as con:
        rows = con.execute(
            "SELECT text, conf, x, y, w, h FROM words WHERE job_id=?", (job_id,)).fetchall()
        return [dict(r) for r in rows]


def stats() -> dict:
    """Library-wide numbers for the Dashboard tab."""
    with _connect() as con:
        row = con.execute(
            "SELECT COUNT(*) AS total, "
            "COALESCE(SUM(status='done'),0) AS done, "
            "COALESCE(SUM(status='error'),0) AS error, "
            "COALESCE(SUM(status='processing'),0) AS processing, "
            "ROUND(AVG(CASE WHEN status='done' THEN mean_conf END),1) AS avg_conf "
            "FROM jobs WHERE archived=0").fetchone()
        boost = con.execute(
            "SELECT COALESCE(SUM(status='pending'),0) AS pending, "
            "COALESCE(SUM(status='answered'),0) AS answered FROM boost_queue").fetchone()
        return {**dict(row), "boost_pending": boost["pending"],
                "boost_answered": boost["answered"]}


def get_job(job_id: int) -> dict | None:
    """Full Job row + its sections, for the result viewer."""
    with _connect() as con:
        job = con.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if job is None:
            return None
        sections = con.execute(
            "SELECT * FROM sections WHERE job_id=? ORDER BY idx", (job_id,)).fetchall()
        result = dict(job)
        result["sections"] = [dict(s) for s in sections]
        return result


def pending_boost_count() -> int:
    """How many sections are waiting for AI Boost (shown in the UI)."""
    with _connect() as con:
        return con.execute("SELECT COUNT(*) FROM boost_queue WHERE status='pending'").fetchone()[0]


def pending_boost_items(limit: int = 100) -> list[dict]:
    """Oldest pending Boost Queue items, ready to send when online."""
    with _connect() as con:
        rows = con.execute(
            "SELECT bq.*, s.idx AS section_idx, j.job_dir "
            "FROM boost_queue bq "
            "JOIN sections s ON s.id = bq.section_id "
            "JOIN jobs j ON j.id = bq.job_id "
            "WHERE bq.status='pending' ORDER BY bq.id LIMIT ?",
            (limit,)).fetchall()
        return [dict(r) for r in rows]


def mark_boost_sent(item_id: int) -> None:
    """Flag an item as in-flight so a crash never double-sends it silently."""
    with _connect() as con:
        con.execute("UPDATE boost_queue SET status='sent' WHERE id=?", (item_id,))


def claim_boost(item_id: int) -> bool:
    """Atomically take a pending item (pending → sent). Returns False when some
    other drain (the GUI auto-boost vs a manual/API run) already claimed it, so
    the same crop is never sent to Gemini twice and the daily cap isn't double
    counted (v0.2.0)."""
    with _connect() as con:
        cur = con.execute(
            "UPDATE boost_queue SET status='sent' WHERE id=? AND status='pending'",
            (item_id,))
        return cur.rowcount == 1


def complete_boost(item_id: int, section_id: int, ai_text: str) -> None:
    """Store the AI answer and mark the section boosted (merge step 1)."""
    with _connect() as con:
        con.execute(
            "UPDATE boost_queue SET status='answered', ai_text=?, answered_at=? WHERE id=?",
            (ai_text, datetime.now().isoformat(timespec="seconds"), item_id))
        con.execute("UPDATE sections SET status='boosted' WHERE id=?", (section_id,))


def fail_boost(item_id: int, requeue: bool) -> None:
    """Send failed: requeue (network/quota — try again later) or mark failed for good."""
    with _connect() as con:
        con.execute("UPDATE boost_queue SET status=? WHERE id=?",
                    ("pending" if requeue else "failed", item_id))


def append_boost_to_job(job_id: int, section_idx: int, ai_text: str) -> None:
    """Merge step 2: append the AI reading to the Job's Raw Extract text, clearly labelled."""
    with _connect() as con:
        row = con.execute("SELECT full_text FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            return
        full_text = row["full_text"] or ""
        if "[AI Boost]" not in full_text:
            full_text += "\n\n[AI Boost]"
        full_text += f"\nsection {section_idx}: {ai_text}"
        con.execute("UPDATE jobs SET full_text=? WHERE id=?", (full_text, job_id))
