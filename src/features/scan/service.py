"""Scan pipeline — preprocess → full pass → Sectioned Scan → stitch → Raw Extract.

This is the heart of the eyes: one Source in, maximum-detail Raw Extract out
(result.json + DB rows + queued crops for AI Boost).
"""
import json
import threading
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageOps

from src.core.config import paths
from src.core.config.settings import Settings
from src.core.models.ocr import Word, SectionResult, JobResult
from src.core.services import engine, store
from src.core.utils import imaging, pdfio

SECTION_ZOOM = 3.0  # tiles are scanned at 3x — deep-detail mode (Nick: slower is fine)
RESCUE_ZOOM = 4.0   # rescue pass looks even closer before giving up to the Boost Queue
SPARSE_PSM = 11     # Tesseract sparse-text mode — scattered labels on drawings
RESCUE_MIN_WORD_CONF = 45.0  # rescue-variant words below this are noise (esp. inverted runs)

# Auto language detect (v0.1.3): tha+eng on a Latin-only drawing hallucinates
# stray Thai glyphs ("ง เ ผ ..."). Real Thai text shows as multi-char words —
# when a page has almost none, the whole page re-runs English-only.
LATIN_ONLY_MIN_WORD_LEN = 3    # a "real" Thai word has at least this many chars
LATIN_ONLY_MAX_COUNT = 3       # fewer real Thai words than this AND
LATIN_ONLY_MAX_RATIO = 0.02    # below this share of confident words → eng only


def _has_thai(text: str) -> bool:
    return any("฀" <= ch <= "๿" for ch in text)  # Thai Unicode block


def latin_only_page(words: list[Word]) -> bool:
    """True when the first full pass shows no real Thai text — only glyph noise."""
    confident = [w for w in words if w.conf >= 60]
    if not confident:
        return False  # nothing readable yet — keep both languages, sections decide
    thai_real = [w for w in confident
                 if _has_thai(w.text)
                 and len("".join(w.text.split())) >= LATIN_ONLY_MIN_WORD_LEN]
    return (len(thai_real) < LATIN_ONLY_MAX_COUNT
            and len(thai_real) / len(confident) < LATIN_ONLY_MAX_RATIO)


class ScanCancelled(Exception):
    """Raised inside the pipeline when the user cancels a running scan."""


class ScanControl:
    """Pause/cancel signalling for a running scan — checked between sections
    and between PDF pages, so the stop is clean (finished pages are kept)."""

    def __init__(self):
        self._pause = threading.Event()
        self._cancel = threading.Event()

    def pause(self) -> None:
        self._pause.set()

    def resume(self) -> None:
        self._pause.clear()

    def cancel(self) -> None:
        self._cancel.set()
        self._pause.clear()  # a paused scan must wake up to see the cancel

    @property
    def paused(self) -> bool:
        return self._pause.is_set()

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()

    def checkpoint(self) -> None:
        """Block while paused; raise ScanCancelled once cancel is requested."""
        while self._pause.is_set() and not self._cancel.is_set():
            time.sleep(0.2)
        if self._cancel.is_set():
            raise ScanCancelled("scan cancelled by user")


def run_source(source_path: str, settings: Settings,
               on_progress=lambda msg: None, on_page_done=None,
               control: ScanControl | None = None,
               skip_pages: set[int] | None = None) -> list[JobResult]:
    """Process one Source of any supported kind. A PDF becomes one Job per page
    (source recorded as path#page=N); an image stays a single Job.

    `on_page_done(result)` fires after EACH Job finishes — multi-page PDFs
    stream results page by page instead of going silent for the whole batch.
    `control` enables pause/cancel; a cancel keeps every already-finished page
    and returns the partial result list. `skip_pages` resumes an interrupted
    batch — those page numbers are not scanned again."""
    if not pdfio.is_pdf(source_path):
        try:
            result = run_job(source_path, settings, on_progress, control=control)
        except ScanCancelled:
            return []
        if on_page_done:
            on_page_done(result)
        return [result]
    total = pdfio.page_count(source_path)
    results = []
    for i in range(total):
        if skip_pages and (i + 1) in skip_pages:
            on_progress(f"Page {i + 1}/{total} already scanned — skipped.")
            continue
        on_progress(f"PDF page {i + 1}/{total}...")
        try:
            if control:
                control.checkpoint()
            page_img = pdfio.render_page(source_path, i)
            result = run_job(
                f"{source_path}#page={i + 1}", settings,
                on_progress=lambda m, p=i + 1: on_progress(f"Page {p}/{total}: {m}"),
                image=page_img, page=i + 1, pages=total, control=control)
        except ScanCancelled:
            break  # finished pages stay valid; the cut-off job is marked error
        if on_page_done:
            on_page_done(result)
        results.append(result)
    return results


def run_job(source_path: str, settings: Settings,
            on_progress=lambda msg: None, *, image=None,
            page: int | None = None, pages: int | None = None,
            control: ScanControl | None = None) -> JobResult:
    """Process one Source end-to-end and persist everything to the Shared Store.

    `image` lets a caller hand in an already-rendered PIL image (PDF pages);
    `source_path` is then a label like file.pdf#page=2, not an openable file.
    """
    job_dir = _new_job_dir()
    job_id = store.create_job(source_path, str(job_dir), settings.languages)
    try:
        result = _scan(source_path, job_dir, job_id, settings, on_progress,
                       image=image, control=control)
        result.page, result.pages = page, pages
        _persist(result, settings)
        return result
    except Exception as exc:
        store.fail_job(job_id, repr(exc))
        raise


def _new_job_dir() -> Path:
    """Create the next jobs/job_NNNN folder."""
    existing = [int(p.name.split("_")[1]) for p in paths.JOBS_DIR.glob("job_*") if p.name.split("_")[1].isdigit()]
    job_dir = paths.JOBS_DIR / f"job_{(max(existing) + 1 if existing else 1):04d}"
    job_dir.mkdir(parents=True)
    return job_dir


def _scan(source_path: str, job_dir: Path, job_id: int, settings: Settings,
          on_progress, image=None, control: ScanControl | None = None) -> JobResult:
    """The actual pipeline: full-image pass + per-section zoomed pass, then stitch."""
    on_progress("Loading image...")
    if image is not None:
        img = image
        img.save(job_dir / "original.png")  # rendered PDF page — keep a real image for the Heart
    else:
        img = Image.open(source_path)
        img.save(job_dir / ("original" + Path(source_path).suffix.lower()))
    pre = imaging.preprocess(img, settings.upscale_min_side)

    on_progress("Full-image pass...")
    langs = settings.languages
    full_words = engine.ocr_words(pre, langs)
    if settings.auto_language and "tha" in langs and latin_only_page(full_words):
        # English-only drawing: a tha+eng pass sprays stray Thai glyphs over the
        # line work. Re-run clean — real Thai pages keep both languages.
        langs = "eng"
        on_progress("English-only page detected — dropping Thai pass...")
        full_words = engine.ocr_words(pre, langs)
    # Second full pass in sparse-text mode — catches scattered drawing labels
    # the block-layout pass misses; stitch-dedupe removes the doubles.
    full_words += engine.ocr_words(pre, langs, psm=SPARSE_PSM)

    rows, cols = ((settings.grid_rows, settings.grid_cols) if not settings.auto_grid
                  else imaging.auto_grid(pre.size, settings.grid_rows, settings.grid_cols))
    boxes = imaging.grid_sections(pre.size, rows, cols, settings.overlap_pct)
    sections: list[SectionResult] = []
    all_words: list[Word] = list(full_words)
    for idx, box in enumerate(boxes):
        if control:
            control.checkpoint()  # pause holds here; cancel raises ScanCancelled
        on_progress(f"Section {idx + 1}/{len(boxes)}...")
        tile = imaging.crop_section(pre, box, zoom=SECTION_ZOOM)
        # Dual pass per tile too (block + sparse) — deep-detail mode.
        raw = (engine.ocr_words(tile, langs)
               + engine.ocr_words(tile, langs, psm=SPARSE_PSM))
        words = _dedupe([w.shifted(box[0], box[1], scale=SECTION_ZOOM) for w in raw])
        mean_conf = _mean_conf(words)
        status = "ok"
        crop_path = None
        rescued = False
        rescue_method = None
        blank = not words and imaging.ink_ratio(tile) < 0.002  # truly empty area, nothing to boost
        # Rescue runs below the quality bar (rescue_trigger_conf), not just the queue bar —
        # mid-confidence sections get the deep treatment too.
        trigger = max(settings.rescue_trigger_conf, settings.low_conf_threshold)
        if not blank and settings.rescue_enabled and (not words or mean_conf < trigger):
            on_progress(f"Section {idx + 1}/{len(boxes)} rescue...")
            r_words, r_conf, rescue_method = _rescue(pre, box, langs, words)
            if r_words and r_conf > mean_conf:
                words, mean_conf = r_words, r_conf
                rescued = mean_conf >= settings.low_conf_threshold
            if not rescued:
                rescue_method = None
        unclear = not blank and (not words or mean_conf < settings.low_conf_threshold)
        if unclear:
            # Still unclear: keep the crop on disk for the AI Boost pass (CONTEXT invariant)
            status = "unreadable" if not words else "low_conf"
            crop_path = str(job_dir / f"section_{idx:02d}.png")
            tile.save(crop_path)
        sections.append(SectionResult(idx=idx, bbox=box, words=words,
                                      mean_conf=mean_conf, status=status,
                                      crop_path=crop_path, rescued=rescued,
                                      rescue_method=rescue_method if rescued else None))
        all_words.extend(words)

    on_progress("Stitching...")
    merged = _dedupe(all_words)
    return JobResult(
        job_id=job_id, source_path=source_path, job_dir=str(job_dir),
        full_text=_reading_order_text(merged), mean_conf=_mean_conf(merged),
        words=merged, sections=sections, languages_used=langs,
    )


def _rescue(pre, box, langs: str, base_words: list[Word]):
    """Self-rescue an unclear section — deep-detail mode: run EVERY variant and
    merge the union (no early stop; Nick: slower is fine, thoroughness wins).

    Variants: 4x zoom → binarized (Otsu, auto-invert) → sparse-text mode →
    full inversion (light-on-dark patches) → rotated 90/270 (vertical labels).
    Variant words below RESCUE_MIN_WORD_CONF are dropped as noise before merging
    (inverted/rotated runs hallucinate on the wrong polarity). The merge keeps
    the highest-confidence word per spot via the normal stitch dedupe.
    Returns (merged words on full image, conf, winning variant label).
    """
    tile = imaging.crop_section(pre, box, zoom=RESCUE_ZOOM)
    bw = imaging.binarize(tile)
    pool: list[Word] = list(base_words)
    best_method, best_variant_conf = None, 0.0

    for img, method, psm, angle in (
        (tile, "zoom4", None, 0),
        (bw, "zoom4+binarize", None, 0),
        (bw, "zoom4+binarize+sparse", SPARSE_PSM, 0),
        (ImageOps.invert(bw), "zoom4+invert", None, 0),      # light text on dark patches
        (bw.rotate(90, expand=True), "rotate90", None, 90),   # vertical drawing labels
        (bw.rotate(270, expand=True), "rotate270", None, 270),
    ):
        raw = engine.ocr_words(img, langs, psm=psm)
        if angle:
            raw = [Word(w.text, w.conf, *imaging.unrotate_box((w.x, w.y, w.w, w.h),
                                                              angle, tile.size))
                   for w in raw]
        words = [w.shifted(box[0], box[1], scale=RESCUE_ZOOM)
                 for w in raw if w.conf >= RESCUE_MIN_WORD_CONF]
        conf = _mean_conf(words)
        if words and conf > best_variant_conf:
            best_variant_conf, best_method = conf, method
        pool.extend(words)

    merged = _dedupe(pool)
    return merged, _mean_conf(merged), best_method


def _persist(result: JobResult, settings: Settings) -> None:
    """Write result.json + DB rows; queue unclear sections for AI Boost."""
    for sec in result.sections:
        section_id = store.add_section(result.job_id, sec.idx, list(sec.bbox),
                                       sec.crop_path, sec.mean_conf, sec.status)
        if sec.status in ("low_conf", "unreadable"):
            local_text = " ".join(w.text for w in sec.words)
            store.queue_boost(result.job_id, section_id, sec.crop_path, local_text)
    store.add_words(result.job_id, result.words)
    store.finish_job(result.job_id, result.full_text, result.mean_conf)

    payload = {
        "job_id": result.job_id,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "source_path": result.source_path,
        "languages": settings.languages,
        "languages_used": result.languages_used or settings.languages,  # additive (v0.1.3)
        "mean_conf": result.mean_conf,
        "full_text": result.full_text,
        "words": [asdict(w) for w in result.words],
        "sections": [{**asdict(s), "words": [asdict(w) for w in s.words]}
                     for s in result.sections],
    }
    if result.page is not None:  # PDF Sources only — additive fields, schema-safe
        payload["page"] = result.page
        payload["pages"] = result.pages
    (Path(result.job_dir) / "result.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")


def _mean_conf(words: list[Word]) -> float:
    """Average confidence of a word list (0 when empty)."""
    return round(sum(w.conf for w in words) / len(words), 1) if words else 0.0


def _dedupe(words: list[Word]) -> list[Word]:
    """Merge duplicates from overlapping passes — same spot, keep the highest confidence."""
    kept: list[Word] = []
    for w in sorted(words, key=lambda w: -w.conf):
        if not any(_overlaps(w, k) for k in kept):
            kept.append(w)
    return kept


def _overlaps(a: Word, b: Word, thresh: float = 0.5) -> bool:
    """True when two word boxes cover the same area (IoU over the smaller box)."""
    ix = max(0, min(a.x + a.w, b.x + b.w) - max(a.x, b.x))
    iy = max(0, min(a.y + a.h, b.y + b.h) - max(a.y, b.y))
    inter = ix * iy
    smaller = min(a.w * a.h, b.w * b.h) or 1
    return inter / smaller > thresh


def _reading_order_text(words: list[Word]) -> str:
    """Assemble words into lines top-to-bottom, left-to-right (natural reading order)."""
    if not words:
        return ""
    lines: list[list[Word]] = []
    for w in sorted(words, key=lambda w: (w.y, w.x)):
        for line in lines:
            ref = line[0]
            if abs((w.y + w.h / 2) - (ref.y + ref.h / 2)) < max(ref.h, w.h) * 0.6:
                line.append(w)
                break
        else:
            lines.append([w])
    return "\n".join(" ".join(w.text for w in sorted(line, key=lambda w: w.x))
                     for line in lines)
