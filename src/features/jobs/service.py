"""Jobs feature logic — read-side queries over the Shared Store for the UI."""
from src.core.services import store


def recent_jobs() -> list[dict]:
    """Latest jobs for the list view."""
    return store.list_jobs(limit=50)


def job_detail(job_id: int) -> dict | None:
    """One job with its sections, for the detail pane."""
    return store.get_job(job_id)


def boost_pending() -> int:
    """Count of sections waiting for AI Boost."""
    return store.pending_boost_count()
