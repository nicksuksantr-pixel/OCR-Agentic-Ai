"""unrotate_box round-trip smoke — verify the inverse rotation against PIL itself.

The rescue pass OCRs a tile rotated with ``Image.rotate(angle, expand=True)`` and
must map every word box found on the rotated tile back onto the UNrotated tile
(``imaging.unrotate_box``). A wrong inverse mis-places rescued words and can flip
a section ok<->low_conf.

The existing smoke_rescue.py only checks unrotate_box against hand-computed
constants — the same mental model as the formula, so a shared mistake would pass
both. This test instead round-trips through PIL's OWN affine: it paints a known
rectangle on a blank tile, rotates the tile with the exact call the pipeline
uses, reads the rotated rectangle's getbbox() as the "found box", feeds that to
unrotate_box, and asserts the result matches the original rectangle (±tolerance
for the integer rounding PIL introduces on the rotated bbox edges). This is an
independent check: if the formula is wrong, the round-trip fails here.

90 and 270 are the angles unrotate_box actually remaps (and the only ones the
rescue pass rotates by); 0 and 180 are returned unchanged, so they are asserted
as pass-through — 0 still lands on the original box because no rotation moved it.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import os as _os, tempfile as _tempfile  # noqa: E402 — isolate the test store
_os.environ.setdefault("OCR_AGENTIC_DATA_DIR",
                       str(Path(_tempfile.gettempdir()) / "ocr-agentic-tests"))

sys.stdout.reconfigure(encoding="utf-8")

from PIL import Image, ImageDraw  # noqa: E402

from src.core.utils import imaging  # noqa: E402

TOLERANCE = 2  # px — PIL rounds the rotated bbox edges; the inverse is exact otherwise


def check(ok: bool, label: str) -> bool:
    print(("✅" if ok else "❌"), label)
    return ok


def _close(a, b) -> bool:
    """True when every coordinate of two [x, y, w, h] boxes is within TOLERANCE."""
    return all(abs(p - q) <= TOLERANCE for p, q in zip(a, b))


def _roundtrip(angle: int):
    """Paint a known rectangle, rotate the tile by `angle` (expand=True, the
    pipeline's call), and recover its box with unrotate_box.

    Returns (original_box, found_box, recovered_box), all [x, y, w, h]:
      original  — the rectangle as drawn on the unrotated tile
      found     — the rectangle's bbox on the rotated tile (what OCR would report)
      recovered — unrotate_box(found) mapped back to the unrotated tile
    """
    ow, oh = 200, 120                       # unrotated tile size (orig_size)
    rx, ry, rw, rh = 40, 25, 90, 35         # the "word" box on the tile
    original = (rx, ry, rw, rh)

    # Black field, white-ink rectangle: getbbox() returns the bbox of NON-ZERO
    # pixels, so the rectangle must be the non-zero region (a white page would
    # make every pixel non-zero and getbbox() would return the whole canvas).
    # This also mirrors the pipeline, where the rotated tile fed to OCR is
    # binarize()'s ink-on-field output, not a white page.
    tile = Image.new("L", (ow, oh), 0)
    ImageDraw.Draw(tile).rectangle((rx, ry, rx + rw - 1, ry + rh - 1), fill=255)

    rotated = tile.rotate(angle, expand=True)  # SAME call the rescue pass makes
    bbox = rotated.getbbox()                    # (left, top, right, bottom) of the ink
    found = (bbox[0], bbox[1], bbox[2] - bbox[0], bbox[3] - bbox[1])  # → [x, y, w, h]

    recovered = imaging.unrotate_box(found, angle, (ow, oh))
    return original, found, recovered


def main() -> None:
    all_ok = True
    for angle in (0, 90, 180, 270):
        original, found, recovered = _roundtrip(angle)
        if angle in (90, 270):
            # The real check: the inverse must land back on the original rectangle.
            ok = _close(recovered, original)
        elif angle == 0:
            # No rotation moved the box; unrotate_box passes it through unchanged,
            # so it must still equal the original rectangle.
            ok = recovered == found and _close(recovered, original)
        else:  # 180 — not remapped by unrotate_box; assert it is returned verbatim
            ok = recovered == found
        all_ok &= check(ok, f"unrotate_box round-trips {angle}° via PIL "
                            f"(orig={original}, found={found}, got={recovered})")

    print("\nUNROTATE SMOKE:", "PASS" if all_ok else "FAIL")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
