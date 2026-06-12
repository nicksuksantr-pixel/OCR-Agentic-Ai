"""Generate the app icon (assets/icon.ico + icon.png) — the project identity.

Design: a clean geometric "scanning eye" — dark slate rounded square, white
almond eye, blue iris with a glint, and a cyan scan line crossing the pupil.
Drawn at 512 px with supersampling, exported as a multi-size .ico (16-256) so
the taskbar, title bar, installer and shortcuts all stay crisp (branding #3;
pitfall #4 in the installer reference: single-size icons look broken).
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ASSETS = Path(__file__).resolve().parents[1] / "assets"
S = 1024  # supersample canvas; final master is 512


def draw_master() -> Image.Image:
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # Rounded-square badge — dark slate with a subtle two-tone vertical blend
    radius = S // 5
    top, bottom = (28, 34, 46, 255), (17, 21, 30, 255)
    for y in range(S):
        t = y / S
        col = tuple(round(a + (b - a) * t) for a, b in zip(top, bottom))
        d.line([(0, y), (S, y)], fill=col)
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, S - 1, S - 1), radius=radius, fill=255)
    img.putalpha(mask)
    d = ImageDraw.Draw(img)

    cx, cy = S // 2, S // 2
    # Almond eye outline (two intersecting circle arcs), thick white stroke
    eye_w, eye_h = int(S * 0.74), int(S * 0.46)
    stroke = S // 28
    bbox_top = (cx - eye_w // 2, cy - eye_h + int(S * 0.115),
                cx + eye_w // 2, cy + int(S * 0.115))
    bbox_bot = (cx - eye_w // 2, cy - int(S * 0.115),
                cx + eye_w // 2, cy + eye_h - int(S * 0.115))
    d.arc(bbox_top, start=25, end=155, fill=(238, 242, 248, 255), width=stroke)
    d.arc(bbox_bot, start=205, end=335, fill=(238, 242, 248, 255), width=stroke)

    # Iris — blue ring + deep core
    iris_r = int(S * 0.155)
    d.ellipse((cx - iris_r, cy - iris_r, cx + iris_r, cy + iris_r),
              fill=(0, 132, 226, 255))
    core_r = int(iris_r * 0.62)
    d.ellipse((cx - core_r, cy - core_r, cx + core_r, cy + core_r),
              fill=(10, 26, 44, 255))
    # Glint
    g_r = int(iris_r * 0.22)
    gx, gy = cx + int(iris_r * 0.38), cy - int(iris_r * 0.40)
    d.ellipse((gx - g_r, gy - g_r, gx + g_r, gy + g_r), fill=(255, 255, 255, 235))

    # Cyan scan line across the eye — the "OCR" signature
    line_h = S // 44
    d.rounded_rectangle((int(S * 0.16), cy - line_h // 2,
                         int(S * 0.84), cy + line_h // 2),
                        radius=line_h // 2, fill=(0, 220, 255, 215))
    return img.resize((512, 512), Image.LANCZOS)


def main() -> None:
    ASSETS.mkdir(exist_ok=True)
    master = draw_master()
    master.resize((256, 256), Image.LANCZOS).save(ASSETS / "icon.png")
    master.save(ASSETS / "icon.ico",
                sizes=[(16, 16), (24, 24), (32, 32), (48, 48),
                       (64, 64), (128, 128), (256, 256)])
    print("icon written:", ASSETS / "icon.ico")


if __name__ == "__main__":
    sys.exit(main())
