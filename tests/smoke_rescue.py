"""Self-rescue smoke — prove the new local powers actually read what v0.0.6 couldn't.

Builds a torture image: tiny dense text, a vertical (90°-rotated) label, and
white-on-black text — then checks the pipeline recovers them locally (no AI).
Also unit-checks auto_grid scaling and unrotate_box round-trips.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

from PIL import Image, ImageDraw, ImageFont

from src.core.config import paths
from src.core.config import settings as settings_mod
from src.core.services import engine
from src.core.utils import imaging
from src.features.scan import service


def check(ok: bool, label: str) -> bool:
    print(("✅" if ok else "❌"), label)
    return ok


def make_torture_image(path: Path) -> None:
    """One drawing-like page with the three classic killers."""
    img = Image.new("L", (1600, 1200), 255)
    d = ImageDraw.Draw(img)
    big = ImageFont.truetype("arial.ttf", 44)
    tiny = ImageFont.truetype("arial.ttf", 13)

    d.text((50, 30), "TORTURE TEST SHEET 01", font=big, fill=0)
    d.text((60, 300), "Relay K-77 coil 24VDC", font=tiny, fill=0)  # tiny but normal

    # Vertical label (reads bottom-to-top, like a cable tag along a line)
    vert = Image.new("L", (260, 34), 255)
    ImageDraw.Draw(vert).text((4, 2), "RISER CABLE R-405", font=ImageFont.truetype("arial.ttf", 22), fill=0)
    img.paste(vert.rotate(90, expand=True), (1380, 350))

    # White text on a black box (title block style)
    d.rectangle((100, 850, 700, 990), fill=0)
    d.text((130, 890), "PANEL DB-9 MAIN", font=big, fill=255)

    img.save(path)


def main() -> None:
    paths.ensure_dirs()
    settings = settings_mod.load()
    settings.auto_grid = True
    settings.rescue_enabled = True
    err = engine.configure(settings)
    if err:
        print("ENGINE ERROR:", err)
        sys.exit(1)

    # Unit: auto_grid scales with size, respects minimum and cap
    all_ok = check(imaging.auto_grid((1600, 1200), 3, 3) == (3, 3), "auto_grid keeps 3x3 minimum")
    all_ok &= check(imaging.auto_grid((5200, 4100), 3, 3) == (5, 6), "auto_grid grows for big scans")
    all_ok &= check(imaging.auto_grid((20000, 20000), 3, 3) == (7, 7), "auto_grid caps at 7x7")

    # Unit: unrotate_box maps rotated word boxes back exactly
    tile = Image.new("L", (200, 100), 255)
    box90 = imaging.unrotate_box((10, 20, 30, 8), 90, tile.size)   # found on CCW-rotated tile
    all_ok &= check(box90 == (200 - 20 - 8, 10, 8, 30), "unrotate_box 90° math")
    box270 = imaging.unrotate_box((10, 20, 30, 8), 270, tile.size)
    all_ok &= check(box270 == (20, 100 - 10 - 30, 8, 30), "unrotate_box 270° math")

    # Pipeline: the torture sheet
    test_img = paths.DATA_DIR / "smoke_rescue.png"
    make_torture_image(test_img)
    result = service.run_job(str(test_img), settings, on_progress=lambda m: print(" ", m))
    text = result.full_text.upper()

    all_ok &= check("TORTURE" in text, "baseline big text read")
    all_ok &= check("RELAY" in text or "K-77" in text, "tiny text read")
    all_ok &= check("RISER" in text or "R-405" in text, "vertical label read (rotate rescue)")
    all_ok &= check("PANEL" in text or "DB-9" in text, "white-on-black read (invert rescue)")
    rescued = [(s.idx, s.rescue_method) for s in result.sections if s.rescued]
    print("rescued sections:", rescued or "none")
    print("mean_conf:", result.mean_conf, "| sections:", len(result.sections))

    print("\nRESCUE SMOKE:", "PASS" if all_ok else "FAIL")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
