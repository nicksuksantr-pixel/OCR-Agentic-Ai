"""Self-introduction — how this program tells Open-Claw (the Heart) who it is.

One machine-readable document describing identity, capabilities, data locations
and both hand-off interfaces, so the Heart can self-configure without a human
copying paths around. Delivered through both doors:
  - file:  data\\introduction.json — rewritten on every app start
  - API:   GET /introduce — same payload, always current
English only (CONTEXT language policy). Extending this is safe; renaming or
removing fields is a breaking change (V-Log).
"""
from datetime import datetime

from src.core.config import paths
from src.core.config.settings import Settings

INTRODUCTION_PATH = paths.DATA_DIR / "introduction.json"


def build_introduction(settings: Settings, version: str) -> dict:
    """Everything the Heart needs to know about the eyes, in one payload."""
    return {
        "app": "OCR-Agentic-Ai",
        "version": version,
        "role": "eyes",
        "purpose": ("Maximum-detail OCR on photos, technical drawings, diagrams "
                    "and PDFs. Produces Raw Extracts (text + positions + "
                    "confidence). Extracts everything, interprets nothing — "
                    "interpretation belongs to Open-Claw."),
        "intended_consumer": "Open-Claw (the Heart)",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "languages_read": ["tha", "eng"],
        "system_language": "English (all labels, statuses, symbol tags)",
        "offline_first": True,
        "shared_store": {
            "db_path": str(paths.DB_PATH),
            "db_engine": "sqlite3",
            "jobs_dir": str(paths.JOBS_DIR),
            "inbox_dir": str(paths.INBOX_DIR),
            "tables": {
                "jobs": "one row per Source: status processing|done|error, full_text, mean_conf",
                "sections": "Sectioned-Scan tiles: bbox, mean_conf, status ok|low_conf|queued|boosted|unreadable",
                "words": "merged final words with x/y/w/h positions and 0-100 confidence",
                "boost_queue": "unclear sections: status pending|sent|answered|failed, local_text, ai_text",
            },
            "job_folder_layout": "jobs/job_NNNN/: original.<ext> + section_NN.png crops + result.json (full Raw Extract incl. ai_boosts). A PDF Source makes one job per page: source recorded as path#page=N, result.json gains additive page/pages fields, original.png is the rendered page",
        },
        "interfaces": {
            "watched_folder": {
                "how": f"Drop an image file into {paths.INBOX_DIR} — it is scanned "
                       "automatically; the original moves to inbox/processed (or inbox/failed).",
                "enabled": settings.watch_inbox,
                "formats": ["png", "jpg", "jpeg", "bmp", "tif", "tiff", "webp", "pdf"],
            },
            "api": {
                "base_url": f"http://127.0.0.1:{settings.api_port}",
                "enabled": settings.api_enabled,
                "endpoints": {
                    "GET /health": "liveness + version + pending boost count",
                    "GET /introduce": "this document",
                    "GET /jobs?limit=N": "newest jobs",
                    "GET /jobs/{id}": "one job + its sections",
                    "GET /jobs/{id}/result": "full Raw Extract (result.json)",
                    "POST /scan {\"path\": \"<image or pdf>\"}": "scan synchronously, returns job summary (+jobs list, one per PDF page)",
                    "POST /boost/run": "drain the AI Boost queue now",
                },
            },
        },
        "conventions": {
            "symbol_tags": "confident technical symbols appear as English descriptors "
                           "like (diode); uncertain ones are ALWAYS (unknown symbol) — never guessed",
            "ai_boost": "low-confidence sections are upgraded by Gemini when online; "
                        "AI readings are appended to full_text under an [AI Boost] block "
                        "and listed in result.json ai_boosts — local text is never silently rewritten",
            "completeness": "no region is silently dropped: every section is scanned or "
                            "explicitly marked unreadable",
            "self_rescue": "sections below the quality bar run ALL local variants (4x zoom, "
                           "Otsu binarize, inversion for light-on-dark, sparse mode, 90/270 "
                           "rotation for vertical labels) and merge the union before joining "
                           "the Boost Queue; rescued sections carry additive "
                           "rescued/rescue_method fields in result.json",
            "adaptive_grid": "the section grid scales with image size (configured grid is "
                             "the minimum, capped at 7x7) — bigger scans get more tiles",
        },
    }


def write_introduction(settings: Settings, version: str) -> None:
    """Refresh data/introduction.json (called on every app start)."""
    import json
    INTRODUCTION_PATH.write_text(
        json.dumps(build_introduction(settings, version), ensure_ascii=False, indent=1),
        encoding="utf-8")
