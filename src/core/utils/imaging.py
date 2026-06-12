"""Image helpers: preprocessing and Sectioned-Scan tiling (Nick's split-and-stitch idea)."""
from PIL import Image, ImageOps

Image.MAX_IMAGE_PIXELS = None  # drawings can be huge scans; we manage memory via tiling


def preprocess(img: Image.Image, upscale_min_side: int) -> Image.Image:
    """Grayscale + autocontrast + upscale small images so tiny text becomes readable."""
    img = ImageOps.exif_transpose(img)  # respect phone-photo rotation
    gray = ImageOps.autocontrast(img.convert("L"))
    short_side = min(gray.size)
    if 0 < short_side < upscale_min_side:
        scale = upscale_min_side / short_side
        gray = gray.resize((round(gray.width * scale), round(gray.height * scale)),
                           Image.LANCZOS)
    return gray


def content_bbox(img: Image.Image, pad_pct: float = 0.01,
                 dark_threshold: int = 200) -> tuple[int, int, int, int]:
    """Bounding box (x0, y0, x1, y1) of the actual ink on a page, padded a bit.

    Lets the Sectioned Scan grid cover the drawing instead of the empty paper
    margin around it. Falls back to the full image when the page is blank.
    """
    gray = img if img.mode == "L" else img.convert("L")
    box = gray.point(lambda p: 255 if p < dark_threshold else 0).getbbox()
    if box is None:
        return (0, 0, img.width, img.height)
    pad_x, pad_y = round(img.width * pad_pct), round(img.height * pad_pct)
    return (max(0, box[0] - pad_x), max(0, box[1] - pad_y),
            min(img.width, box[2] + pad_x), min(img.height, box[3] + pad_y))


def grid_sections(size: tuple[int, int], rows: int, cols: int,
                  overlap_pct: float) -> list[tuple[int, int, int, int]]:
    """Split (width, height) into rows x cols overlapping boxes [x, y, w, h], row-major order."""
    width, height = size
    tile_w, tile_h = width / cols, height / rows
    ox, oy = tile_w * overlap_pct, tile_h * overlap_pct
    boxes = []
    for r in range(rows):
        for c in range(cols):
            x0 = max(0, round(c * tile_w - ox))
            y0 = max(0, round(r * tile_h - oy))
            x1 = min(width, round((c + 1) * tile_w + ox))
            y1 = min(height, round((r + 1) * tile_h + oy))
            boxes.append((x0, y0, x1 - x0, y1 - y0))
    return boxes


# ---- physical-size grid (v0.1.5) ------------------------------------------
# Text on technical drawings has a roughly constant PHYSICAL height (~2.5-5 mm)
# no matter how big the sheet is, so tiles are sized in millimetres of paper,
# not pixels: an A4 splits ~2x3, an A3 ~3x4, an A0 hits the compute cap.
TILE_TARGET_MM = 110.0   # aim for ~11 cm of paper per tile side
GRID_MAX_CELLS = 7       # compute ceiling per axis (same cap as auto_grid)


def grid_from_mm(size_mm: tuple[float, float],
                 max_cells: int = GRID_MAX_CELLS) -> tuple[int, int]:
    """(rows, cols) for a page measured in millimetres — the real paper size
    decides the split, so the grid is never random-feeling again (Nick)."""
    w_mm, h_mm = size_mm
    rows = min(max(1, round(h_mm / TILE_TARGET_MM)), max_cells)
    cols = min(max(1, round(w_mm / TILE_TARGET_MM)), max_cells)
    return rows, cols


def _profile(img: Image.Image, axis: int) -> list[float]:
    """Mean ink (0..1) per row (axis=1) or per column (axis=0) of a grayscale
    image — pure PIL: resize with BOX averaging collapses the other axis."""
    mask = (img if img.mode == "L" else img.convert("L")).point(
        lambda p: 255 if p < 200 else 0)
    if axis == 0:   # per column
        line = mask.resize((mask.width, 1), Image.BOX)
        return [v / 255.0 for v in line.getdata()]
    line = mask.resize((1, mask.height), Image.BOX)
    return [v / 255.0 for v in line.getdata()]


def frame_interior(img: Image.Image, margin_pct: float = 0.15,
                   line_cover: float = 0.55) -> tuple[int, int, int, int]:
    """Interior (x0, y0, x1, y1) of a drawing's border frame.

    Technical sheets carry a rectangular frame with zone-letter strips (A/B/C..,
    1/2/3..) around the edge; tiling those gives the useless border crops Nick
    flagged. A frame line = a row/col whose ink covers most of the page within
    the outer margin band. The INNERMOST such line on each side bounds the
    content. Sides without a frame line fall back to the content bbox.
    """
    cols = _profile(img, 0)
    rows = _profile(img, 1)
    w, h = img.width, img.height
    bx0, by0, bx1, by1 = content_bbox(img)
    mx, my = round(w * margin_pct), round(h * margin_pct)
    inset = max(2, round(min(w, h) * 0.004))  # step inside the line itself

    def innermost(profile, span, limit, from_end):
        idxs = range(span - 1, span - limit - 1, -1) if from_end else range(limit)
        hits = [i for i in idxs if profile[i] >= line_cover]
        return (min(hits) - inset if from_end else max(hits) + inset) if hits else None

    x0 = innermost(cols, w, mx, False)
    x1 = innermost(cols, w, mx, True)
    y0 = innermost(rows, h, my, False)
    y1 = innermost(rows, h, my, True)
    x0 = bx0 if x0 is None else max(x0, 0)
    y0 = by0 if y0 is None else max(y0, 0)
    x1 = bx1 if x1 is None else min(x1, w)
    y1 = by1 if y1 is None else min(y1, h)
    if x1 - x0 < w * 0.3 or y1 - y0 < h * 0.3:  # implausible frame → trust the ink bbox
        return (bx0, by0, bx1, by1)
    return (x0, y0, x1, y1)


def smart_cuts(profile: list[float], n_tiles: int,
               window_pct: float = 0.3) -> list[int]:
    """Internal cut positions for n_tiles along one axis, each snapped to the
    emptiest spot (whitespace valley) near its uniform target — so tiles split
    BETWEEN content instead of slicing through words/rows."""
    span = len(profile)
    pitch = span / n_tiles
    win = max(1, round(pitch * window_pct))
    cuts = []
    for k in range(1, n_tiles):
        target = round(k * pitch)
        lo, hi = max(1, target - win), min(span - 1, target + win)
        # emptiest position; ties go to the one closest to the uniform target
        cuts.append(min(range(lo, hi + 1),
                        key=lambda i: (round(profile[i], 3), abs(i - target))))
    return cuts


def smart_grid(img: Image.Image, interior: tuple[int, int, int, int],
               rows: int, cols: int, overlap_pct: float
               ) -> tuple[list[tuple[int, int, int, int]], list[int], list[int]]:
    """Content-aware Sectioned-Scan grid inside the frame interior.

    Returns (boxes [x,y,w,h] row-major, x_cuts, y_cuts) — cuts are absolute
    coordinates, used afterwards for the seam-strip pass.
    """
    x0, y0, x1, y1 = interior
    region = img.crop(interior)
    xs = [x0] + [x0 + c for c in smart_cuts(_profile(region, 0), cols)] + [x1]
    ys = [y0] + [y0 + c for c in smart_cuts(_profile(region, 1), rows)] + [y1]
    ox = (x1 - x0) / cols * overlap_pct
    oy = (y1 - y0) / rows * overlap_pct
    boxes = []
    for r in range(rows):
        for c in range(cols):
            bx0 = max(x0, round(xs[c] - ox))
            by0 = max(y0, round(ys[r] - oy))
            bx1 = min(x1, round(xs[c + 1] + ox))
            by1 = min(y1, round(ys[r + 1] + oy))
            boxes.append((bx0, by0, bx1 - bx0, by1 - by0))
    return boxes, xs[1:-1], ys[1:-1]


def seam_strips(interior: tuple[int, int, int, int], x_cuts: list[int],
                y_cuts: list[int], strip_pct: float = 0.4,
                min_px: int = 300) -> list[tuple[int, int, int, int]]:
    """Strips [x,y,w,h] centred on every internal grid cut — scanned as an
    extra pass so text sitting exactly on a tile seam is read whole (Nick:
    "สแกนระหว่างรอยต่อด้วยจะได้แม่นขึ้น"). Wide enough that a label crossing
    the cut fits inside the strip with room on both sides."""
    x0, y0, x1, y1 = interior
    n_cols, n_rows = len(x_cuts) + 1, len(y_cuts) + 1
    pitch_x, pitch_y = (x1 - x0) / n_cols, (y1 - y0) / n_rows
    sw = round(min(0.6 * pitch_x, max(min_px, pitch_x * strip_pct)))
    sh = round(min(0.6 * pitch_y, max(min_px, pitch_y * strip_pct)))
    strips = [(max(x0, cut - sw // 2), y0,
               min(sw, x1 - max(x0, cut - sw // 2)), y1 - y0) for cut in x_cuts]
    strips += [(x0, max(y0, cut - sh // 2),
                x1 - x0, min(sh, y1 - max(y0, cut - sh // 2))) for cut in y_cuts]
    return strips


def ruled_only(img: Image.Image, line_cover: float = 0.6,
               concentration: float = 0.8) -> bool:
    """True when a tile's ink is almost entirely long straight ruled lines
    (empty table cells / frame work) — nothing for OCR or AI to read.

    Rows/cols whose ink covers most of the tile are "line" pixels; if they
    hold >= `concentration` of all ink, the tile is lines-only.
    """
    cols = _profile(img, 0)
    rows = _profile(img, 1)
    total = sum(rows)
    if total <= 0:
        return True  # no ink at all
    line_ink = (sum(r for r in rows if r >= line_cover) / total
                + sum(c for c in cols if c >= line_cover) / max(sum(cols), 1e-9))
    return min(1.0, line_ink) >= concentration


def auto_grid(size: tuple[int, int], min_rows: int, min_cols: int,
              target_tile: int = 800, max_cells: int = 7) -> tuple[int, int]:
    """Scale the Sectioned-Scan grid with image size — big scans get more tiles.

    Aims for ~target_tile px per tile side, never below the configured minimum
    grid and never above max_cells per axis (compute ceiling).
    """
    width, height = size
    rows = min(max(min_rows, round(height / target_tile)), max_cells)
    cols = min(max(min_cols, round(width / target_tile)), max_cells)
    return rows, cols


def binarize(img: Image.Image) -> Image.Image:
    """Otsu-threshold a grayscale image to clean black-on-white for OCR.

    If the result comes out mostly dark (light text on dark ground), invert it —
    Tesseract wants dark text on a white page.
    """
    gray = img.convert("L")
    hist = gray.histogram()
    total = sum(hist) or 1
    # Otsu: maximize between-class variance over all thresholds.
    sum_all = sum(i * h for i, h in enumerate(hist))
    sum_bg = 0.0
    weight_bg = 0
    best_t, best_var = 128, -1.0
    for t in range(256):
        weight_bg += hist[t]
        if weight_bg == 0:
            continue
        weight_fg = total - weight_bg
        if weight_fg == 0:
            break
        sum_bg += t * hist[t]
        mean_bg = sum_bg / weight_bg
        mean_fg = (sum_all - sum_bg) / weight_fg
        var = weight_bg * weight_fg * (mean_bg - mean_fg) ** 2
        if var > best_var:
            best_var, best_t = var, t
    bw = gray.point(lambda p, t=best_t: 255 if p > t else 0)
    white = bw.histogram()[255]
    if white < (bw.width * bw.height) / 2:  # dark page → light-on-dark source
        bw = ImageOps.invert(bw)
    return bw


def unrotate_box(box: tuple[int, int, int, int], angle: int,
                 orig_size: tuple[int, int]) -> tuple[int, int, int, int]:
    """Map a word box found on a rotated tile back onto the unrotated tile.

    angle is the PIL.rotate(expand=True) angle that produced the rotated tile
    (90 = counter-clockwise, 270 = clockwise). orig_size = unrotated (w, h).
    """
    x, y, w, h = box
    ow, oh = orig_size
    if angle == 90:    # rotated (x,y) came from original (ow - y - h, x)
        return ow - y - h, x, h, w
    if angle == 270:   # rotated (x,y) came from original (y, oh - x - w)
        return y, oh - x - w, h, w
    return box


def ink_ratio(img: Image.Image, dark_threshold: int = 128) -> float:
    """Fraction of dark pixels in a grayscale image — near zero means a blank area."""
    hist = img.convert("L").histogram()
    total = sum(hist) or 1
    return sum(hist[:dark_threshold]) / total


def crop_section(img: Image.Image, box: tuple[int, int, int, int],
                 zoom: float = 2.0) -> Image.Image:
    """Cut one section and zoom it so dense small text gets more pixels for OCR."""
    x, y, w, h = box
    tile = img.crop((x, y, x + w, y + h))
    if zoom != 1.0:
        tile = tile.resize((round(w * zoom), round(h * zoom)), Image.LANCZOS)
    return tile
