"""Shared Store — SQLite database both this app and Open-Claw (the Heart) read.

Schema: jobs (one per Source) · sections (Sectioned Scan tiles) · words (merged
final words with position+confidence) · boost_queue (unclear sections waiting
for AI when online). All labels/fields English per CONTEXT language policy.
"""
import json
import sqlite3
from datetime import datetime

from src.core.config import paths

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
    error       TEXT
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
"""


def _connect() -> sqlite3.Connection:
    """Open the Shared Store DB (created on first use), rows as dicts."""
    con = sqlite3.connect(paths.DB_PATH)
    con.row_factory = sqlite3.Row
    con.executescript(_SCHEMA)
    return con


def create_job(source_path: str, job_dir: str, languages: str) -> int:
    """Insert a new Job row and return its id."""
    with _connect() as con:
        cur = con.execute(
            "INSERT INTO jobs (created_at, source_path, job_dir, languages) VALUES (?,?,?,?)",
            (datetime.now().isoformat(timespec="seconds"), source_path, job_dir, languages),
        )
        return cur.lastrowid


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
    """Latest jobs for the UI list, newest first."""
    with _connect() as con:
        rows = con.execute(
            "SELECT id, created_at, source_path, status, mean_conf FROM jobs ORDER BY id DESC LIMIT ?",
            (limit,)).fetchall()
        return [dict(r) for r in rows]


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
