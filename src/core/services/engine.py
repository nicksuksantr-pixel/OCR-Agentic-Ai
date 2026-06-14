"""Local OCR engine wrapper (Tesseract via pytesseract) — the always-offline primary pass.

Engine choice is isolated here so it can be swapped later without touching features.
"""
import os
import shutil
from pathlib import Path

import pytesseract
from PIL import Image

from src.core.config import paths
from src.core.config.settings import Settings
from src.core.models.ocr import Word

# Set once configure() has succeeded, so the inbox watcher and local API scan
# paths can self-configure (via ensure_configured) without depending on the GUI.
_configured = False


def configure(settings: Settings) -> str | None:
    """Point pytesseract at tesseract.exe; return an error message or None if ready.

    Resolution order: explicit Settings path → bundled copy inside the installed
    app (zero external dependency for end users) → PATH lookup.
    """
    exe = settings.tesseract_path
    if not Path(exe).exists():
        bundled = paths.bundled_tesseract()
        found = shutil.which("tesseract")
        if bundled:
            exe = str(bundled)
        elif found:
            exe = found
        else:
            return ("Tesseract not found. Install it (winget install UB-Mannheim.TesseractOCR) "
                    "or set the path in Settings.")
    pytesseract.pytesseract.tesseract_cmd = exe
    # Language models (eng/tha): first dir that actually has *.traineddata wins
    # (Shared Store tessdata → project data\tessdata → bundled). Env var (not
    # --tessdata-dir) avoids config quoting issues — a quoted path reaches
    # tesseract with the quotes embedded. The project-tree fallback keeps a dev
    # run reading `tha` after the store moved to %LOCALAPPDATA% (v0.2.0).
    for td in paths.tessdata_dirs():
        if any(td.glob("*.traineddata")):
            os.environ["TESSDATA_PREFIX"] = str(td)
            break
    return None


def ensure_configured(settings: Settings) -> str | None:
    """Configure the engine once if it hasn't been yet (idempotent). The inbox
    watcher and the local API call run_job directly, so without this they relied
    on the GUI's ScanView having run configure() first — a fragile construction-
    order side-effect. Now every scan path configures the engine itself."""
    global _configured
    if _configured:
        return None
    err = configure(settings)
    _configured = err is None
    return err


def available_languages() -> list[str]:
    """Languages the engine can actually load right now."""
    try:
        return pytesseract.get_languages(config="")
    except pytesseract.TesseractError:
        return []


ROTATION_THUMB_SIDE = 2200   # rotation check runs on a thumbnail, not the full page
ROTATION_MIN_MARGIN = 1.3    # a turned page must beat upright by this factor
ROTATION_MIN_SCORE = 8.0     # and show real readable text, not noise


def detect_rotation(img: Image.Image) -> int:
    """Degrees CLOCKWISE (0/90/180/270) needed to make the page upright.

    Drawing PDFs often carry a landscape sheet pre-rotated inside a portrait
    page (MSBESB pages 4+) — every label comes out sideways and the local OCR
    reads almost nothing. Tesseract's OSD guesses badly on sparse line work,
    so this is EMPIRICAL: OCR a thumbnail at all four turns and keep the one
    that actually reads best. 0 wins all ties (never rotate on a hunch).
    """
    thumb = img.copy()
    thumb.thumbnail((ROTATION_THUMB_SIDE, ROTATION_THUMB_SIDE))

    def score(im: Image.Image) -> float:
        words = ocr_words(im, "eng", psm=11)  # sparse mode suits drawings
        # confident multi-char words = evidence of a truly readable orientation
        return sum(w.conf for w in words
                   if w.conf >= 60 and len(w.text.strip()) >= 2) / 100.0

    base = score(thumb)
    best_angle, best = 0, base
    for angle in (90, 180, 270):
        s = score(thumb.rotate(-angle, expand=True))
        if s > best:
            best_angle, best = angle, s
    if best_angle and best >= ROTATION_MIN_SCORE and best >= base * ROTATION_MIN_MARGIN:
        return best_angle
    return 0


def ocr_words(img: Image.Image, languages: str, psm: int | None = None) -> list[Word]:
    """OCR one image → words with absolute pixel boxes and 0-100 confidence.

    psm picks a Tesseract page-segmentation mode (None = default 3 auto;
    11 = sparse text — much better for scattered labels on drawings).
    """
    data = pytesseract.image_to_data(
        img, lang=languages, output_type=pytesseract.Output.DICT,
        config=f"--psm {psm}" if psm is not None else "",
    )
    words: list[Word] = []
    for i, text in enumerate(data["text"]):
        text = text.strip()
        conf = float(data["conf"][i])
        if not text or conf < 0:  # conf -1 = layout filler rows, not real words
            continue
        words.append(Word(
            text=text, conf=conf,
            x=data["left"][i], y=data["top"][i],
            w=data["width"][i], h=data["height"][i],
        ))
    return words
