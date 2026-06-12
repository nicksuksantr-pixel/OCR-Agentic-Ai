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
