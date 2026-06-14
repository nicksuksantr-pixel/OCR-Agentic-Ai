"""Headless smoke test for the grid engine — physical-size grid, whole-sheet
content-bbox coverage (no pre-scan crop, v0.2.9), valley-snapped cuts, staggered
offset grid, ruled-only filter, whole-page orientation. Builds a synthetic framed
drawing and asserts each behaviour; exits non-zero on the first failure."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import os as _os, tempfile as _tempfile  # noqa: E402 — isolate the test store
_os.environ.setdefault("OCR_AGENTIC_DATA_DIR",
                       str(Path(_tempfile.gettempdir()) / "ocr-agentic-tests"))

sys.stdout.reconfigure(encoding="utf-8")

from PIL import Image, ImageDraw, ImageFont

from src.core.config import paths
from src.core.config import settings as settings_mod
from src.core.services import engine
from src.core.utils import imaging
from src.features.scan import service

CHECKS = []


def check(name: str, ok: bool, detail: str = "") -> None:
    CHECKS.append(ok)
    print(("  PASS  " if ok else "  FAIL  ") + name + (f" — {detail}" if detail else ""))


def make_framed_drawing(path: Path) -> None:
    """A3-landscape-style sheet: double border frame + zone letters in the band,
    real text only INSIDE the frame, one label sitting exactly on a grid seam."""
    img = Image.new("L", (2400, 1700), 255)
    d = ImageDraw.Draw(img)
    big = ImageFont.truetype("arial.ttf", 46)
    small = ImageFont.truetype("arial.ttf", 28)
    # double frame: outer trim line + inner border, zone letters between them
    d.rectangle((20, 20, 2379, 1679), outline=0, width=3)
    d.rectangle((90, 90, 2309, 1609), outline=0, width=3)
    for i, z in enumerate("ABCD"):
        d.text((40, 220 + i * 380), z, font=big, fill=0)
        d.text((2330, 220 + i * 380), z, font=big, fill=0)
    for i in range(1, 7):
        d.text((180 + (i - 1) * 380, 30), str(i), font=big, fill=0)
        d.text((180 + (i - 1) * 380, 1620), str(i), font=big, fill=0)
    # content INSIDE the frame
    d.text((300, 300), "MAIN SWITCHBOARD 440V", font=big, fill=0)
    d.text((350, 700), "FEEDER PANEL FP-21", font=small, fill=0)
    d.text((1500, 1100), "GENERATOR G3 350KVA", font=small, fill=0)
    # a word centred on the vertical mid-cut of a 2-col grid (x ~ 1200)
    d.text((1080, 900), "SEAMWORD77", font=small, fill=0)
    img.save(path)


def make_ruled_tile() -> Image.Image:
    """Empty table cells — straight ruled lines only, no text."""
    img = Image.new("L", (900, 700), 255)
    d = ImageDraw.Draw(img)
    for y in range(50, 700, 80):
        d.line((0, y, 899, y), fill=0, width=3)
    for x in (0, 300, 600, 899):
        d.line((x, 0, x, 699), fill=0, width=3)
    return img


def make_text_tile() -> Image.Image:
    """Dense unreadable-ish text tile — must NOT be classified ruled-only."""
    img = Image.new("L", (900, 700), 255)
    d = ImageDraw.Draw(img)
    small = ImageFont.truetype("arial.ttf", 22)
    for y in range(40, 660, 40):
        d.text((30, y), "BRKR NSX100N 3C/25mm2 SUPPLY FEEDER", font=small, fill=0)
    return img


def _spans_full(intervals: list[tuple[int, int]], lo: int, hi: int) -> bool:
    """True when the UNION of (start, end) intervals covers [lo, hi] with no gap.

    The offset grid is staggered in BOTH axes, so a main-grid cut is not crossed
    by one full-length tile — it is crossed by a STACK of offset tiles, each
    spanning one band, that together run the whole interior side. That union is
    what actually lets a cut-straddling label be read whole by *some* offset tile,
    so the coverage contract is union-completeness, not a single spanning tile."""
    cursor = lo
    for s, e in sorted(intervals):
        if s > cursor:           # a gap before this interval — a word here is split
            return False
        cursor = max(cursor, e)
        if cursor >= hi:
            return True
    return cursor >= hi


def _offset_covers_all_cuts() -> tuple[bool, str]:
    """For real grid shapes, assert every main-grid cut is crossed by offset tiles
    whose UNION spans the whole interior along that cut's length. Uses smart_grid
    for real cut positions, then walks offset_grid's boxes. Returns (ok, detail)
    for check(). This is the offset grid's true coverage contract — the thing the
    end-to-end SEAMWORD assertion can't isolate (that word is also reachable by
    the full-image pass / main-grid overlap, so SEAMWORD stays green even if the
    offset grid regressed)."""
    for rows, cols in ((3, 4), (2, 2), (7, 7), (3, 2), (1, 5), (5, 1)):
        interior = (90, 70, 2309, 1609)
        x0, y0, x1, y1 = interior
        canvas = Image.new("L", (x1, y1), 255)
        _, x_cuts, y_cuts = imaging.smart_grid(canvas, interior, rows, cols, 0.10)
        boxes = imaging.offset_grid(interior, x_cuts, y_cuts, 0.10)
        for xc in x_cuts:  # vertical cut: tiles straddling it must union to full height
            straddle = [(by, by + bh) for bx, by, bw, bh in boxes if bx < xc < bx + bw]
            if not straddle:
                return False, f"{rows}x{cols}: vertical cut x={xc} not straddled at all"
            if not _spans_full(straddle, y0, y1):
                return False, f"{rows}x{cols}: vertical cut x={xc} has a height gap"
        for yc in y_cuts:  # horizontal cut: straddling tiles must union to full width
            straddle = [(bx, bx + bw) for bx, by, bw, bh in boxes if by < yc < by + bh]
            if not straddle:
                return False, f"{rows}x{cols}: horizontal cut y={yc} not straddled at all"
            if not _spans_full(straddle, x0, x1):
                return False, f"{rows}x{cols}: horizontal cut y={yc} has a width gap"
    return True, "every main cut straddled by offset tiles spanning its full length"


def main() -> None:
    paths.ensure_dirs()
    settings = settings_mod.load()
    err = engine.configure(settings)
    if err:
        print("ENGINE ERROR:", err)
        sys.exit(1)

    # --- pure-imaging checks (no OCR) ---
    rows, cols = imaging.grid_from_mm((210, 297))   # A4 portrait
    check("grid_from_mm A4 = 2x3", (rows, cols) == (3, 2), f"got {rows}x{cols}")
    rows, cols = imaging.grid_from_mm((420, 297))   # A3 landscape
    check("grid_from_mm A3 = 3x4", (rows, cols) == (3, 4), f"got {rows}x{cols}")
    rows, cols = imaging.grid_from_mm((1189, 841))  # A0 landscape → capped
    check("grid_from_mm A0 capped 7x7", (rows, cols) == (7, 7), f"got {rows}x{cols}")

    sheet_path = paths.DATA_DIR / "smoke_grid_sheet.png"
    make_framed_drawing(sheet_path)
    sheet = Image.open(sheet_path)
    # No pre-scan crop (v0.2.9): content_bbox keeps the WHOLE inked sheet —
    # frame, zone band and all — so the left title-block strip is never lost.
    cx0, cy0, cx1, cy1 = imaging.content_bbox(sheet)
    check("content_bbox keeps the whole inked sheet (no document crop)",
          cx0 <= 60 and cy0 <= 60 and cx1 >= 2340 and cy1 >= 1640,
          f"content_bbox=({cx0},{cy0},{cx1},{cy1})")
    # the pipeline works on the preprocessed (upscaled) canvas — expectations
    # below must live in that space
    pre = imaging.preprocess(sheet, settings.upscale_min_side)
    px0, py0, px1, py1 = imaging.content_bbox(pre)
    interior_mm = ((px1 - px0) / pre.width * 420.0,
                   (py1 - py0) / pre.height * 297.0)
    exp_rows, exp_cols = imaging.grid_from_mm(interior_mm)

    check("ruled_only: empty table = True", imaging.ruled_only(make_ruled_tile()))
    check("ruled_only: dense text = False", not imaging.ruled_only(make_text_tile()))

    # valley snap: profile empty at 40-60, content elsewhere → cut lands in the gap
    profile = [1.0] * 100
    for i in range(40, 61):
        profile[i] = 0.0
    cut = imaging.smart_cuts(profile, 2)[0]
    check("smart_cuts snaps to valley", 40 <= cut <= 60, f"cut at {cut}")

    # --- offset-grid coverage GUARANTEE (v0.2.9, the red/blue dual grid) ---
    # The end-to-end SEAMWORD check below proves a straddling word survives, but
    # the full-image pass / main-grid overlap can read that word too — so it does
    # NOT isolate the offset grid (it would stay green if offset_grid regressed).
    # This deterministic check guards the offset grid's actual contract: EVERY
    # main-grid cut is crossed by offset tiles whose UNION spans the interior
    # along the cut's full length (the staggered grid tiles BOTH axes, so a cut is
    # crossed by a stack of bands, not one full-length tile). Without that union,
    # a label split by a cut could fall in a gap and be lost forever.
    check("offset grid covers every main cut, full length",
          *_offset_covers_all_cuts())
    # Degenerate grids must not crash and must stay bounded (a 1-col page has no
    # vertical cut to cover; the offset pass must still be valid, never explode).
    deg = imaging.offset_grid((90, 70, 1200, 1609), [], [350, 700], 0.10)  # 1 column
    check("offset grid safe on a 1-column grid (no x_cuts)",
          isinstance(deg, list) and len(deg) > 0, f"{len(deg)} tiles")
    deg1 = imaging.offset_grid((90, 70, 900, 800), [], [], 0.10)           # 1x1
    check("offset grid safe & bounded on a 1x1 grid (no cuts)",
          isinstance(deg1, list) and len(deg1) <= 4, f"{len(deg1)} tiles")

    # --- full pipeline on the framed sheet (A3 landscape physical size) ---
    print("\nScanning framed sheet (as A3 landscape)...")
    result = service.run_job(str(sheet_path), settings,
                             on_progress=lambda m: print("   ", m),
                             page_size_mm=(420.0, 297.0))
    text = result.full_text.upper()
    check("content read", "SWITCHBOARD" in text and "FEEDER" in text)
    # The staggered offset grid must read a word straddling a main-grid cut as ONE
    # token, not two fragments (the cut sits mid-tile in the offset grid). We assert
    # un-split-ness (a single >=9-char SEAMWORD* token), which tolerates a digit
    # glyph misread ("77"->"/") unrelated to the dual-grid logic; a real split would
    # leave only the 8-char "SEAMWORD" fragment.
    cut_tokens = [w.text for w in result.words if w.text.upper().startswith("SEAMWORD")]
    check("cut-straddling word read whole (one token, offset grid)",
          any(len(t) >= 9 for t in cut_tokens), f"tokens: {cut_tokens}")
    check(f"grid is {exp_rows}x{exp_cols} from physical size",
          len(result.sections) == exp_rows * exp_cols,
          f"{len(result.sections)} sections")
    inside = all(s.bbox[0] >= px0 - 40 and s.bbox[1] >= py0 - 40
                 and s.bbox[0] + s.bbox[2] <= px1 + 40
                 and s.bbox[1] + s.bbox[3] <= py1 + 40 for s in result.sections)
    check("all tiles inside content bbox", inside)
    queued = [s for s in result.sections if s.status in ("low_conf", "unreadable")]
    check("no border/empty tiles queued", len(queued) == 0,
          f"queued: {[(s.idx, s.status) for s in queued]}")
    check("page_size_mm recorded", result.page_size_mm == (420.0, 297.0))

    # --- whole-page rotation: same sheet turned 90° must come back upright ---
    print("\nScanning the same sheet rotated 90°...")
    rot_path = paths.DATA_DIR / "smoke_grid_rot.png"
    sheet.rotate(90, expand=True).save(rot_path)  # CCW → needs 90° CW fix
    result_rot = service.run_job(str(rot_path), settings,
                                 on_progress=lambda m: None,
                                 page_size_mm=(297.0, 420.0))
    check("rotation detected", result_rot.page_rotation in (90, 270),
          f"page_rotation={result_rot.page_rotation}")
    check("rotated page still read",
          "SWITCHBOARD" in result_rot.full_text.upper())

    print(f"\n{sum(CHECKS)}/{len(CHECKS)} checks passed")
    sys.exit(0 if all(CHECKS) else 1)


if __name__ == "__main__":
    main()
