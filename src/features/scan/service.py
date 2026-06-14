"""Scan pipeline — preprocess → full pass → Sectioned Scan → stitch → Raw Extract.

This is the heart of the eyes: one Source in, maximum-detail Raw Extract out
(result.json + DB rows + queued crops for AI Boost).
"""
import json
import shutil
import threading
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageOps

from src.core.config import paths
from src.core.config.settings import Settings
from src.core.models.ocr import Word, SectionResult, JobResult
from src.core.services import engine, gemini, store
from src.core.utils import imaging, pdfio

SECTION_ZOOM = 3.0  # tiles are scanned at 3x — deep-detail mode (Nick: slower is fine)
ZOOM_MAX_SIDE = 8000  # sanity cap: a zoomed tile never exceeds this side in px
PREVIEW_MAX = 1100  # live-preview thumbnail max side sent to the Scan tab (v0.2.2)
RESCUE_ZOOM = 4.0   # rescue pass looks even closer before giving up to the Boost Queue
SPARSE_PSM = 11     # Tesseract sparse-text mode — scattered labels on drawings
RESCUE_MIN_WORD_CONF = 45.0  # rescue-variant words below this are noise (esp. inverted runs)
SUPPORTED_EXT = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp", ".pdf"}  # the one
                # allow-list every ingest door (GUI picker, inbox watcher, API) checks against
_SCAN_LOCK = threading.Lock()  # one scan at a time across GUI / inbox / API (v0.2.0)
BLANK_MAX_INK = 0.004        # tile ink below this with no words = empty paper, skip rescue
LINE_ONLY_MAX_INK = 0.02     # no words even after rescue + ink below this = just frame/border
                             # lines — do NOT queue for AI or keep a crop (v0.1.4, Nick:
                             # "it keeps photographing the document edges, what for?")

# Auto language detect (v0.1.3, fixed v0.2.0): tha+eng on a Latin-only drawing
# makes the tha model hallucinate stray Thai glyphs ("ง เ ผ ฬ ฯ ไ ..."). The old
# gate counted "real Thai words" and was defeated by the very noise it targeted
# (3+ multi-char Thai blobs on a dense drawing flipped it off). The fix measures
# CHARACTER MASS: a page that is overwhelmingly Latin letters is English-only,
# no matter how many phantom Thai blobs the noise produced.
LATIN_ONLY_MAX_THAI_SHARE = 0.10  # ≤10% Thai-char mass among confident text → eng only

# Standalone single-char line artifacts (ruled lines, dimension ticks, table
# borders) the sparse/rescue passes read as "|", "/", etc. Dropping these is not
# "guessing a symbol" — the section crop is still queued for AI Boost when it
# falls below threshold, so nothing meaningful is lost (v0.2.0).
_NOISE_SINGLE = set("|¦/\\_~`^¬")


def _has_thai(text: str) -> bool:
    return any("฀" <= ch <= "๿" for ch in text)  # Thai Unicode block


def _thai_char_count(text: str) -> int:
    return sum(1 for ch in text if "฀" <= ch <= "๿")


def _latin_char_count(text: str) -> int:
    return sum(1 for ch in text if ch.isascii() and ch.isalpha())


def latin_only_page(words: list[Word]) -> bool:
    """True when confident text is overwhelmingly Latin — the page is English
    and the Thai pass only adds glyph noise. Mass-based so it fires on both
    dense drawings (many short Thai blobs) and sparse ones; a genuinely Thai
    page has Thai characters dominating and stays tha+eng."""
    confident = [w for w in words if w.conf >= 60]
    if not confident:
        return False  # nothing readable yet — keep both languages, sections decide
    latin = sum(_latin_char_count(w.text) for w in confident)
    thai = sum(_thai_char_count(w.text) for w in confident)
    if latin + thai == 0:
        return False  # only digits/symbols — no language signal, keep both
    return latin > 0 and thai / (latin + thai) < LATIN_ONLY_MAX_THAI_SHARE


def _mostly_thai(text: str) -> bool:
    """True when a token is majority Thai codepoints — a phantom glyph on a page
    already judged English-only. The token-level safety net the pipeline lacked:
    even if one pass slipped through with tha, no Thai escapes an English page."""
    stripped = [c for c in text if not c.isspace()]
    if not stripped:
        return False
    return sum(1 for c in stripped if "฀" <= c <= "๿") > len(stripped) / 2


def _is_line_noise(text: str) -> bool:
    """True for standalone ruled-line artifacts ('|', '///', '¦¦') — never a
    meaningful OCR word on these drawings."""
    t = "".join(text.split())
    if not t:
        return True
    if len(t) == 1 and t in _NOISE_SINGLE:
        return True
    return set(t) <= {"|", "¦"}  # pipe runs like "|||"


class ScanCancelled(Exception):
    """Raised inside the pipeline when the user cancels a running scan."""


class ScanControl:
    """Pause/cancel signalling for a running scan — checked between sections
    and between PDF pages, so the stop is clean (finished pages are kept)."""

    def __init__(self):
        self._pause = threading.Event()
        self._cancel = threading.Event()
        self._paused_total = 0.0    # accumulated seconds spent paused (for honest ETA)
        self._paused_at: float | None = None

    def pause(self) -> None:
        if not self._pause.is_set():
            self._paused_at = time.time()
            self._pause.set()

    def resume(self) -> None:
        if self._pause.is_set():
            if self._paused_at is not None:
                self._paused_total += time.time() - self._paused_at
                self._paused_at = None
            self._pause.clear()

    def cancel(self) -> None:
        self._cancel.set()
        self._pause.clear()  # a paused scan must wake up to see the cancel

    def paused_seconds(self) -> float:
        """Total time spent paused so far — subtracted from elapsed so the ETA
        does not balloon while a scan sits paused (v0.2.2)."""
        extra = (time.time() - self._paused_at) if self._paused_at is not None else 0.0
        return self._paused_total + extra

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
               skip_pages: set[int] | None = None,
               on_event=lambda e: None) -> list[JobResult]:
    """Process one Source of any supported kind. A PDF becomes one Job per page
    (source recorded as path#page=N); an image stays a single Job.

    `on_page_done(result)` fires after EACH Job finishes — multi-page PDFs
    stream results page by page instead of going silent for the whole batch.
    `control` enables pause/cancel; a cancel keeps every already-finished page
    and returns the partial result list. `skip_pages` resumes an interrupted
    batch — those page numbers are not scanned again. `on_event` is the live
    structured feed (page image + per-section bbox/text) the Scan tab renders so
    a long single page no longer shows an empty box (v0.2.2); each event is
    stamped with the page/pages it belongs to here."""
    if not pdfio.is_pdf(source_path):
        try:
            result = run_job(source_path, settings, on_progress, control=control,
                             on_event=lambda e: on_event({**e, "page": 1, "pages": 1}))
        except ScanCancelled:
            return []
        if on_page_done:
            on_page_done(result)
        return [result]
    results = []
    with pdfio.PdfReader(source_path) as pdf:  # opened once, not per page (v0.2.0)
        total = pdf.page_count()
        for i in range(total):
            if skip_pages and (i + 1) in skip_pages:
                on_progress(f"Page {i + 1}/{total} already scanned — skipped.")
                continue
            on_progress(f"PDF page {i + 1}/{total}...")
            try:
                if control:
                    control.checkpoint()
                page_img = pdf.render_page(i)
                # Real paper size measured BEFORE any scanning — it drives the
                # Sectioned-Scan grid (A4 vs A0 must not split the same; v0.1.5).
                size_mm = pdf.page_size_mm(i)
                result = run_job(
                    f"{source_path}#page={i + 1}", settings,
                    on_progress=lambda m, p=i + 1: on_progress(f"Page {p}/{total}: {m}"),
                    image=page_img, page=i + 1, pages=total, control=control,
                    page_size_mm=size_mm,
                    on_event=lambda e, p=i + 1, t=total: on_event({**e, "page": p, "pages": t}))
            except ScanCancelled:
                break  # finished pages stay valid; the cut-off job is marked error
            if on_page_done:
                on_page_done(result)
            results.append(result)
    return results


def run_job(source_path: str, settings: Settings,
            on_progress=lambda msg: None, *, image=None,
            page: int | None = None, pages: int | None = None,
            control: ScanControl | None = None,
            page_size_mm: tuple[float, float] | None = None,
            on_event=lambda e: None) -> JobResult:
    """Process one Source end-to-end and persist everything to the Shared Store.

    `image` lets a caller hand in an already-rendered PIL image (PDF pages);
    `source_path` is then a label like file.pdf#page=2, not an openable file.
    `page_size_mm` = physical paper size (PDF pages); image files fall back to
    their DPI metadata, and pixel heuristics only when nothing is known.
    """
    # Make the engine self-sufficient: the inbox watcher and the local API reach
    # here without the GUI's ScanView having configured Tesseract first, so
    # configure it ourselves (idempotent). Without this a scan via those doors
    # threw a raw 'tesseract is not installed' whenever the GUI tab had not
    # initialised the engine first (audit P1).
    cfg_err = engine.ensure_configured(settings)
    if cfg_err:
        raise RuntimeError(cfg_err)

    # Resume hygiene: clear any previous error/processing attempt for this exact
    # page before re-scanning, so a resumed batch never piles up duplicate jobs
    # for the same page (audit: done_pages only saw 'done', so errored pages were
    # re-scanned as brand-new jobs each cycle).
    _clear_failed_attempts(source_path)

    # Folder name comes from the DB id (monotonic, never reused) — not a glob of
    # on-disk folders. This ends the job_0002 → job_0002_1_1_1 collision chain
    # that made archived jobs look like they "came back" (v0.2.0).
    with _SCAN_LOCK:
        job_id = store.create_job(source_path, "", settings.languages)
        job_dir = paths.JOBS_DIR / f"job_{job_id:04d}"
        job_dir.mkdir(parents=True, exist_ok=True)
        store.update_job_dir(job_id, str(job_dir))
        try:
            result = _scan(source_path, job_dir, job_id, settings, on_progress,
                           image=image, control=control, page_size_mm=page_size_mm,
                           on_event=on_event)
            result.page, result.pages = page, pages
            _persist(result, settings)
            return result
        except ScanCancelled:
            store.fail_job(job_id, "cancelled by user")
            _write_error_result(job_dir, job_id, source_path, "cancelled by user", page, pages)
            raise
        except Exception as exc:
            store.fail_job(job_id, repr(exc))
            _write_error_result(job_dir, job_id, source_path, repr(exc), page, pages)
            raise


def _clear_failed_attempts(source_path: str) -> None:
    """Remove prior non-done jobs for this exact Source/page (folder + rows) so a
    resume replaces a failed attempt instead of stacking another duplicate."""
    for j in store.jobs_for_exact_source(source_path):
        if j["status"] != "done":
            shutil.rmtree(j["job_dir"], ignore_errors=True)
            store.delete_job(j["id"])


def _write_error_result(job_dir: Path, job_id: int, source_path: str,
                        error: str, page: int | None, pages: int | None) -> None:
    """Write a minimal result.json for a failed/cancelled job so the Open-Claw
    contract (every job folder has a result.json) holds and GET /jobs/{id}/result
    returns the error instead of a bare 404 (v0.2.0)."""
    payload = {"job_id": job_id, "source_path": source_path, "status": "error",
               "error": error,
               "created_at": datetime.now().isoformat(timespec="seconds"),
               "full_text": "", "words": [], "sections": []}
    if page is not None:
        payload["page"], payload["pages"] = page, pages
    try:
        (Path(job_dir) / "result.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass  # best-effort — the DB row already records the error


def _scan(source_path: str, job_dir: Path, job_id: int, settings: Settings,
          on_progress, image=None, control: ScanControl | None = None,
          page_size_mm: tuple[float, float] | None = None,
          on_event=lambda e: None) -> JobResult:
    """The actual pipeline: orient → full pass → physical-size content grid →
    per-section zoomed pass → seam pass → stitch."""
    on_progress("Loading image...")
    if image is not None:
        img = image
        img.save(job_dir / "original.png")  # rendered PDF page — keep a real image for the Heart
    else:
        img = Image.open(source_path)
        img.save(job_dir / ("original" + Path(source_path).suffix.lower()))
        if page_size_mm is None:
            dpi = (img.info.get("dpi") or (0, 0))[0]
            if dpi and dpi > 1:  # scanned images carry real DPI → real paper size
                page_size_mm = (img.width / dpi * 25.4, img.height / dpi * 25.4)
    pre = imaging.preprocess(img, settings.upscale_min_side)

    # Whole-page orientation FIRST — drawing PDFs often hold a landscape sheet
    # rotated inside a portrait page; every later step needs upright text.
    rotation = engine.detect_rotation(pre)
    if rotation:
        on_progress(f"Page is rotated {rotation}° — turning upright...")
        pre = pre.rotate(-rotation, expand=True)
        if rotation in (90, 270) and page_size_mm:
            page_size_mm = (page_size_mm[1], page_size_mm[0])

    on_progress("Full-image pass...")
    langs = settings.languages
    auto_lang = settings.auto_language and "tha" in settings.languages
    full_words = engine.ocr_words(pre, langs)
    if auto_lang and latin_only_page(full_words):
        # English-only drawing: a tha+eng pass sprays stray Thai glyphs over the
        # line work. Re-run clean — real Thai pages keep both languages.
        langs = "eng"
        on_progress("English-only page detected — dropping Thai pass...")
        full_words = engine.ocr_words(pre, langs)
    # Second full pass in sparse-text mode — catches scattered drawing labels
    # the block-layout pass misses; stitch-dedupe removes the doubles.
    full_words += engine.ocr_words(pre, langs, psm=SPARSE_PSM)

    # Grid INSIDE the drawing frame (zone strips/borders are never tiled), with
    # rows/cols decided by the real paper size whenever we know it.
    interior = imaging.frame_interior(pre)
    in_w, in_h = interior[2] - interior[0], interior[3] - interior[1]
    if page_size_mm:
        interior_mm = (in_w / pre.width * page_size_mm[0],
                       in_h / pre.height * page_size_mm[1])
        rows, cols = imaging.grid_from_mm(interior_mm)
    elif settings.auto_grid:  # nothing measurable — pixel heuristic fallback
        rows, cols = imaging.auto_grid((in_w, in_h),
                                       settings.grid_rows, settings.grid_cols)
    else:
        rows, cols = settings.grid_rows, settings.grid_cols
    boxes, x_cuts, y_cuts = imaging.smart_grid(pre, interior, rows, cols,
                                               settings.overlap_pct)

    # Live preview for the Scan tab: a downscaled copy of the upright page (same
    # coordinate space as the section boxes) so the UI can show the page and
    # highlight each tile as it is read, instead of an empty box for the whole
    # multi-minute page (v0.2.2). `size` lets the view scale the bboxes.
    preview = pre.copy()
    preview.thumbnail((PREVIEW_MAX, PREVIEW_MAX))
    on_event({"kind": "page_ready", "image": preview,
              "size": (pre.width, pre.height), "sections": len(boxes)})

    tiles: list[dict] = []
    all_words: list[Word] = list(full_words)
    for idx, box in enumerate(boxes):
        if control:
            control.checkpoint()  # pause holds here; cancel raises ScanCancelled
        on_progress(f"Section {idx + 1}/{len(boxes)}...")
        on_event({"kind": "section", "idx": idx, "sections": len(boxes), "bbox": box})
        zoom = _tile_zoom(box)
        tile = imaging.crop_section(pre, box, zoom=zoom)
        # Dual pass per tile too (block + sparse) — deep-detail mode.
        raw = (engine.ocr_words(tile, langs)
               + engine.ocr_words(tile, langs, psm=SPARSE_PSM))
        words = _dedupe([w.shifted(box[0], box[1], scale=zoom) for w in raw])
        mean_conf = _mean_conf(words)
        rescued = False
        rescue_method = None
        ink = imaging.ink_ratio(tile)
        blank = not words and ink < BLANK_MAX_INK  # truly empty area, nothing to boost
        # Rescue runs below the quality bar (rescue_trigger_conf), not just the queue bar —
        # mid-confidence sections get the deep treatment too.
        trigger = max(settings.rescue_trigger_conf, settings.low_conf_threshold)
        if not blank and settings.rescue_enabled and (not words or mean_conf < trigger):
            on_progress(f"Section {idx + 1}/{len(boxes)} rescue...")
            r_words, r_conf, rescue_method = _rescue(pre, box, langs, words, control=control)
            if r_words and r_conf > mean_conf:
                words, mean_conf = r_words, r_conf
                rescued = mean_conf >= settings.low_conf_threshold
            if not rescued:
                rescue_method = None
        # Tiles that are only frame/table LINES: nothing readable after every
        # rescue variant and the ink is straight ruled lines — not text. No AI
        # queue, no crop on disk (empty table cells used to burn AI quota).
        line_only = not words and (ink < LINE_ONLY_MAX_INK
                                   or imaging.ruled_only(tile))
        on_event({"kind": "section_text", "idx": idx, "sections": len(boxes),
                  "text": " ".join(w.text for w in words),
                  "conf": int(round(mean_conf or 0))})
        tiles.append(dict(idx=idx, box=box, zoom=zoom, blank=blank,
                          line_only=line_only, rescued=rescued,
                          rescue_method=rescue_method))
        all_words.extend(words)

    # Seam pass — words sitting exactly on a grid cut are split across two
    # tiles; a strip centred on every cut reads them whole, dedupe keeps the
    # best copy (Nick: "สแกนระหว่างรอยต่อด้วยจะได้แม่นขึ้น").
    strips = imaging.seam_strips(interior, x_cuts, y_cuts)
    for n, strip in enumerate(strips):
        if control:
            control.checkpoint()
        if imaging.ink_ratio(imaging.crop_section(pre, strip, zoom=1.0)) < BLANK_MAX_INK:
            continue  # nothing crosses this seam
        on_progress(f"Seam {n + 1}/{len(strips)}...")
        zoom = _tile_zoom(strip)
        seam_tile = imaging.crop_section(pre, strip, zoom=zoom)
        raw = engine.ocr_words(seam_tile, langs, psm=SPARSE_PSM)
        all_words.extend(w.shifted(strip[0], strip[1], scale=zoom) for w in raw
                         if w.conf >= RESCUE_MIN_WORD_CONF)

    on_progress("Stitching...")
    merged = _dedupe(all_words)

    # Re-judge English-only against the FULL stitched evidence, not just the
    # first (weakest) full pass — the sparse/tile/rescue passes hallucinate Thai
    # far harder, and the old verdict was made before they ran. Then drop any
    # Thai token that slipped through: the safety net the pipeline lacked. A
    # phantom Thai glyph is a wrong symbol, so removing it is correct — the
    # section crop is still queued for AI Boost when it's genuinely unclear.
    eng_only = auto_lang and (langs == "eng" or latin_only_page(merged))
    if eng_only:
        langs = "eng"
        merged = [w for w in merged if not _mostly_thai(w.text)]
    merged = [w for w in merged if not _is_line_noise(w.text)]

    # Section verdicts come AFTER the stitch, from the best merged knowledge —
    # a tile that only saw half a label is fine when the seam pass or the full
    # pass read that area confidently (no more queueing already-solved tiles).
    sections: list[SectionResult] = []
    for t in tiles:
        bx, by, bw, bh = t["box"]
        words_eff = [w for w in merged
                     if bx <= w.x + w.w / 2 <= bx + bw
                     and by <= w.y + w.h / 2 <= by + bh]
        conf_eff = _mean_conf(words_eff)
        status = "ok"
        crop_path = None
        if (not t["blank"] and not t["line_only"]
                and (not words_eff or conf_eff < settings.low_conf_threshold)):
            # Still unclear: keep the crop on disk for the AI Boost pass (CONTEXT invariant)
            status = "unreadable" if not words_eff else "low_conf"
            crop_path = str(job_dir / f"section_{t['idx']:02d}.png")
            imaging.crop_section(pre, t["box"], zoom=t["zoom"]).save(crop_path)
        sections.append(SectionResult(
            idx=t["idx"], bbox=t["box"], words=words_eff, mean_conf=conf_eff,
            status=status, crop_path=crop_path, rescued=t["rescued"],
            rescue_method=t["rescue_method"] if t["rescued"] else None))

    return JobResult(
        job_id=job_id, source_path=source_path, job_dir=str(job_dir),
        full_text=_reading_order_text(merged), mean_conf=_mean_conf(merged),
        words=merged, sections=sections, languages_used=langs,
        page_rotation=rotation, page_size_mm=page_size_mm,
        no_text=not merged,  # finished fine but nothing readable (blank/photo) — not a failure
    )


def _tile_zoom(box: tuple[int, int, int, int]) -> float:
    """Zoom for one tile: SECTION_ZOOM, eased off only when the zoomed tile
    would exceed the ZOOM_MAX_SIDE sanity cap (huge physical-size tiles)."""
    side = max(box[2], box[3]) or 1
    return min(SECTION_ZOOM, max(1.0, ZOOM_MAX_SIDE / side))


def _rescue(pre, box, langs: str, base_words: list[Word],
            control: "ScanControl | None" = None):
    """Self-rescue an unclear section — deep-detail mode: run EVERY variant and
    merge the union (no early stop; Nick: slower is fine, thoroughness wins).

    Variants: 4x zoom → binarized (Otsu, auto-invert) → sparse-text mode →
    full inversion (light-on-dark patches) → rotated 90/270 (vertical labels).
    Variant words below RESCUE_MIN_WORD_CONF are dropped as noise before merging
    (inverted/rotated runs hallucinate on the wrong polarity). The merge keeps
    the highest-confidence word per spot via the normal stitch dedupe.
    `control` lets Pause/Cancel respond BETWEEN the six variants too, not only
    between sections — a deep rescue is the slowest single step, so without this
    a paused scan kept grinding for seconds (Nick, v0.2.2 pause responsiveness).
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
        if control:
            control.checkpoint()  # pause holds here between variants; cancel raises
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
    # Only enqueue boost work that can actually drain: AI Boost must be ENABLED
    # AND a key present. Checking the key alone (v0.2.5) still let the queue swell
    # when the user turned Boost OFF but kept a key — the auto-drain (gated on
    # ai_boost_enabled) would then never empty it (audit P2). The local Raw
    # Extract is still written in full below — nothing local is dropped, and the
    # section crop stays on disk so enabling Boost + a re-scan can still boost it.
    boost_ready = settings.ai_boost_enabled and gemini.read_api_key() is not None
    for sec in result.sections:
        section_id = store.add_section(result.job_id, sec.idx, list(sec.bbox),
                                       sec.crop_path, sec.mean_conf, sec.status)
        if boost_ready and sec.status in ("low_conf", "unreadable"):
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
        "page_rotation": result.page_rotation,                          # additive (v0.1.5)
        "page_size_mm": (list(result.page_size_mm)                      # additive (v0.1.5)
                         if result.page_size_mm else None),
        "mean_conf": result.mean_conf,
        "no_text": result.no_text,                                      # additive (v0.2.2)
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
    """Merge duplicates from overlapping passes — same spot, keep the highest
    confidence. One exception (v0.1.5, the seam fix): a whole word arriving
    after its own higher-confidence FRAGMENTS (a tile cut through the label,
    pieces like "7 7" used to kill "SEAMWORD77") evicts those pieces instead
    of dying as their "duplicate"."""
    kept: list[Word] = []
    for w in sorted(words, key=lambda w: -w.conf):
        frags = [k for k in kept
                 if _contains(w, k) and len(w.text) >= 1.5 * len(k.text)
                 and w.conf >= k.conf - 15]
        if frags:  # w is the whole word these pieces came from
            kept = [k for k in kept if k not in frags]
        if not any(_overlaps(w, k) for k in kept):
            kept.append(w)
    return kept


def _inter(a: Word, b: Word) -> int:
    ix = max(0, min(a.x + a.w, b.x + b.w) - max(a.x, b.x))
    iy = max(0, min(a.y + a.h, b.y + b.h) - max(a.y, b.y))
    return ix * iy


def _overlaps(a: Word, b: Word, thresh: float = 0.5) -> bool:
    """True when two word boxes cover the same area (IoU over the smaller box)."""
    smaller = min(a.w * a.h, b.w * b.h) or 1
    return _inter(a, b) / smaller > thresh


def _contains(outer: Word, inner: Word, frac: float = 0.7) -> bool:
    """True when most of `inner`'s box lies inside `outer`'s box."""
    return _inter(outer, inner) / ((inner.w * inner.h) or 1) >= frac


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
