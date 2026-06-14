"""Headless smoke for the v0.2.3 reliability hardening (from the Tester audit):
AI-Boost merge atomicity + crash-recovery reconciliation + per-section idempotency,
and the additive secondary indexes. Isolates its own store (never the real library)."""
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("OCR_AGENTIC_DATA_DIR",
                      str(Path(tempfile.gettempdir()) / "ocr-agentic-tests-harden"))
sys.stdout.reconfigure(encoding="utf-8")

from src.core.config import paths
from src.core.services import store


def _fresh_boost_job(section_idx: int):
    """Create a done job with one queued (unclear) section; return ids + item id."""
    jid = store.create_job("harden.png", "", "eng")
    jd = paths.JOBS_DIR / f"job_{jid:04d}"
    jd.mkdir(parents=True, exist_ok=True)
    store.update_job_dir(jid, str(jd))
    store.finish_job(jid, "LOCAL ONLY TEXT", 80.0)
    sid = store.add_section(jid, section_idx, [0, 0, 10, 10],
                            str(jd / f"section_{section_idx:02d}.png"), 40.0, "low_conf")
    store.queue_boost(jid, sid, str(jd / f"section_{section_idx:02d}.png"), "garbled local")
    item = next(i["id"] for i in store.pending_boost_items() if i["job_id"] == jid)
    return jid, sid, item


def main() -> None:
    paths.ensure_dirs()
    checks: dict[str, bool] = {}

    # 1) atomic answer+merge folds ai_text into full_text in one transaction
    jid, sid, item = _fresh_boost_job(5)
    store.complete_boost_atomic(item, sid, jid, 5, "CLEAN AI READING")
    ft = store.get_job(jid)["full_text"]
    checks["atomic merge writes full_text"] = "[AI Boost]" in ft and "section 5: CLEAN AI READING" in ft
    # ...and is idempotent per section (a re-run never duplicates the line)
    store.complete_boost_atomic(item, sid, jid, 5, "CLEAN AI READING")
    checks["merge idempotent (no dup line)"] = store.get_job(jid)["full_text"].count("section 5:") == 1

    # 2) reconciliation repairs an answered-but-unmerged row (the pre-atomic crash window:
    #    answer saved to boost_queue, process died before the full_text merge)
    jid2, sid2, item2 = _fresh_boost_job(7)
    store.complete_boost(item2, sid2, "RECOVER THIS READING")  # answer ONLY, no merge
    before = store.get_job(jid2)["full_text"] or ""
    repaired = store.reconcile_boost_merges()
    after = store.get_job(jid2)["full_text"] or ""
    checks["pre-reconcile full_text is missing it"] = "RECOVER THIS READING" not in before
    checks["reconcile fills the lost reading"] = repaired >= 1 and "RECOVER THIS READING" in after
    store.reconcile_boost_merges()  # a second pass must change nothing
    checks["reconcile is idempotent"] = \
        store.get_job(jid2)["full_text"].count("RECOVER THIS READING") == 1

    # 2b) v0.2.6: a multi-line AI reading is collapsed to ONE line, so an ai_text
    #     that itself contains a "section N:"-looking line can NOT spoof the
    #     idempotency guard into dropping a later section's real reading (audit P1).
    jid3, sid3, item3 = _fresh_boost_job(5)
    store.complete_boost_atomic(item3, sid3, jid3, 5, "FIVE LINE1\nsection 7: DECOY")
    ft5 = store.get_job(jid3)["full_text"]
    checks["multiline ai_text collapsed to one line"] = \
        "section 5: FIVE LINE1 section 7: DECOY" in ft5
    sid3b = store.add_section(jid3, 7, [0, 0, 10, 10], None, 40.0, "low_conf")
    store.queue_boost(jid3, sid3b,
                      str(paths.JOBS_DIR / f"job_{jid3:04d}" / "section_07.png"), "x")
    item3b = next(i["id"] for i in store.pending_boost_items() if i["job_id"] == jid3)
    store.complete_boost_atomic(item3b, sid3b, jid3, 7, "GENUINE SEVEN")
    checks["decoy header does not drop real section 7"] = \
        "section 7: GENUINE SEVEN" in store.get_job(jid3)["full_text"]

    # 3) additive secondary indexes exist (Open-Claw hot read path)
    con = sqlite3.connect(paths.DB_PATH)
    have = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    con.close()
    want = {"idx_words_job", "idx_sections_job", "idx_boost_status", "idx_jobs_archived"}
    checks["secondary indexes created"] = want <= have

    for j in (jid, jid2, jid3):
        store.delete_job(j)

    failed = [n for n, ok in checks.items() if not ok]
    for n, ok in checks.items():
        print(("✅" if ok else "❌"), n)
    print(f"\nHARDEN SMOKE: {'FAIL' if failed else 'PASS'}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
