"""AI Boost sender — drains the Boost Queue through Gemini, throttled to free tier.

Offline-first invariant: this only UPGRADES finished Raw Extracts. Any network
failure requeues the item and stops the run — nothing local is ever blocked.
Throttle: ≥4.2 s between requests (≈14 RPM < 15) and a daily request budget
tracked in data/boost_usage.json keyed by the Pacific date (free tier resets
at midnight Pacific ≈ 14:00-15:00 Thai).
"""
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.core.config import paths
from src.core.config.settings import Settings
from src.core.services import gemini, store

USAGE_PATH = paths.DATA_DIR / "boost_usage.json"
SECONDS_BETWEEN_REQUESTS = 4.2
# Pacific approximated as UTC-7 (PDT). Off by 1h half the year — fine for a soft cap.
_PACIFIC_OFFSET = timedelta(hours=-7)


@dataclass
class BoostRunSummary:
    """What one drain run did — shown in the UI and logged."""
    sent: int = 0
    answered: int = 0
    failed: int = 0
    stopped_reason: str = ""          # empty = queue drained
    errors: list[str] = field(default_factory=list)


def send_pending(settings: Settings, on_progress=lambda msg: None) -> BoostRunSummary:
    """Send every pending Boost Queue item to Gemini, oldest first, until done,
    budget exhausted, or the network gives out."""
    summary = BoostRunSummary()
    if not gemini.read_api_key():
        summary.stopped_reason = "No Gemini API key — set it in Settings."
        return summary

    items = store.pending_boost_items()
    if not items:
        summary.stopped_reason = "Boost Queue is empty."
        return summary

    for n, item in enumerate(items):
        if _used_today() >= settings.boost_daily_cap:
            summary.stopped_reason = (f"Daily cap reached ({settings.boost_daily_cap} requests) — "
                                      "resumes after the free-tier reset (≈14:00-15:00 Thai).")
            break
        if n > 0:
            time.sleep(SECONDS_BETWEEN_REQUESTS)  # stay under 15 RPM

        on_progress(f"Boosting section {item['section_idx']} of job {item['job_id']} "
                    f"({n + 1}/{len(items)})...")
        if not Path(item["crop_path"]).exists():
            store.fail_boost(item["id"], requeue=False)
            summary.failed += 1
            summary.errors.append(f"item {item['id']}: crop file missing")
            continue

        store.mark_boost_sent(item["id"])
        summary.sent += 1
        _count_request()  # counts the attempt — quota is spent even when the call fails
        try:
            ai_text = gemini.boost_section(item["crop_path"], item["local_text"],
                                           settings.gemini_model)
        except Exception as exc:
            # Network/quota/API problem: requeue and stop — try again next time online.
            store.fail_boost(item["id"], requeue=True)
            summary.sent -= 1
            summary.stopped_reason = f"Send failed, item requeued: {exc}"
            summary.errors.append(repr(exc))
            break

        store.complete_boost(item["id"], item["section_id"], ai_text)
        store.append_boost_to_job(item["job_id"], item["section_idx"], ai_text)
        _update_result_json(item["job_dir"], item["section_idx"], ai_text)
        summary.answered += 1

    return summary


def _update_result_json(job_dir: str, section_idx: int, ai_text: str) -> None:
    """Merge step 3: record the AI reading in the job folder's result.json."""
    result_path = Path(job_dir) / "result.json"
    if not result_path.exists():
        return
    try:
        payload = json.loads(result_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return  # never let a corrupt file kill the boost run
    boosts = payload.setdefault("ai_boosts", [])
    boosts.append({"section_idx": section_idx, "ai_text": ai_text,
                   "answered_at": datetime.now().isoformat(timespec="seconds")})
    result_path.write_text(json.dumps(payload, ensure_ascii=False, indent=1),
                           encoding="utf-8")


def _pacific_date() -> str:
    """Today's date where the free-tier counter lives."""
    return (datetime.now(timezone.utc) + _PACIFIC_OFFSET).date().isoformat()


def _read_usage() -> dict:
    if USAGE_PATH.exists():
        try:
            usage = json.loads(USAGE_PATH.read_text(encoding="utf-8"))
            if usage.get("date") == _pacific_date():
                return usage
        except json.JSONDecodeError:
            pass
    return {"date": _pacific_date(), "count": 0}


def _used_today() -> int:
    """Requests already spent in the current Pacific day."""
    return _read_usage()["count"]


def _count_request() -> None:
    usage = _read_usage()
    usage["count"] += 1
    USAGE_PATH.write_text(json.dumps(usage), encoding="utf-8")
