"""Headless smoke test — generate a labeled test image, run the full pipeline, print the result."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import os as _os, tempfile as _tempfile  # noqa: E402 — isolate the test store
_os.environ.setdefault("OCR_AGENTIC_DATA_DIR",
                       str(Path(_tempfile.gettempdir()) / "ocr-agentic-tests"))

sys.stdout.reconfigure(encoding="utf-8")  # Windows console defaults to cp1252 — Thai text would crash print

from PIL import Image, ImageDraw, ImageFont

from src.core.config import paths
from src.core.config import settings as settings_mod
from src.core.services import engine
from src.features.scan import service


def make_test_image(path: Path) -> None:
    """Draw a fake 'drawing' with big and tiny English text in scattered corners."""
    img = Image.new("L", (1200, 900), 255)
    d = ImageDraw.Draw(img)
    big = ImageFont.truetype("arial.ttf", 40)
    small = ImageFont.truetype("arial.ttf", 14)
    d.text((40, 30), "MAIN SWITCHBOARD 440V", font=big, fill=0)
    d.text((60, 200), "Breaker CB-101 rating 250A", font=small, fill=0)
    d.text((820, 240), "Cable 3x95 mm2", font=small, fill=0)
    d.text((100, 600), "Generator No.2 standby", font=small, fill=0)
    d.text((850, 820), "DWG-E-4412 Rev.C", font=small, fill=0)
    d.rectangle((30, 180, 1150, 700), outline=0, width=2)
    img.save(path)


def main() -> None:
    paths.ensure_dirs()
    settings = settings_mod.load()
    err = engine.configure(settings)
    if err:
        print("ENGINE ERROR:", err)
        sys.exit(1)
    print("Engine languages:", engine.available_languages())

    test_img = paths.DATA_DIR / "smoke_test.png"
    make_test_image(test_img)
    result = service.run_job(str(test_img), settings, on_progress=lambda m: print(" ", m))

    print("\n--- RAW EXTRACT ---")
    print("mean_conf:", result.mean_conf, "| words:", len(result.words))
    print(result.full_text)
    flagged = [s for s in result.sections if s.status != "ok"]
    print("flagged sections:", [(s.idx, s.status) for s in flagged])
    print("job dir:", result.job_dir)


if __name__ == "__main__":
    main()
