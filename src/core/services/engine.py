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
    # Language models (eng/tha): user data dir wins, else the bundled set.
    # Env var (not --tessdata-dir) avoids config quoting issues — a quoted
    # path reaches tesseract with the quotes embedded.
    if any(paths.TESSDATA_DIR.glob("*.traineddata")):
        os.environ["TESSDATA_PREFIX"] = str(paths.TESSDATA_DIR)
    elif paths.bundled_tessdata():
        os.environ["TESSDATA_PREFIX"] = str(paths.bundled_tessdata())
    return None


def available_languages() -> list[str]:
    """Languages the engine can actually load right now."""
    try:
        return pytesseract.get_languages(config="")
    except pytesseract.TesseractError:
        return []


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
