"""Generate the mascot — "Scout", the little one-eyed scanner robot.

Branding rule #3: the ICON (scanning eye) is the identity — taskbar / installer
exe / shortcuts. The MASCOT is the helper — welcome surfaces: the Scan tab and
the installer wizard pages. Same family: Scout's single big lens eye reuses the
icon's blue iris + cyan scan line, so the two read as one brand.

Outputs:
  assets/mascot.png            512x512 RGBA (in-app)
  build/stage/wizard.bmp       164x314 Inno WizardImageFile (welcome/finish)
  build/stage/wizard_small.bmp 55x55  Inno WizardSmallImageFile (header)
"""
import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
S = 1024  # supersample; final 512

INK = (30, 36, 48, 255)          # outline slate
BODY = (224, 230, 238, 255)      # warm light body
BODY_SHADE = (196, 204, 216, 255)
IRIS = (0, 132, 226, 255)        # same blue as the icon
CORE = (10, 26, 44, 255)
CYAN = (0, 220, 255, 255)


def rr(d, box, r, **kw):
    d.rounded_rectangle(box, radius=r, **kw)


def draw_scout() -> Image.Image:
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    w = S // 90  # outline weight
    cx = S // 2

    # Antenna with a cyan "signal" tip
    d.line([(cx, int(S * 0.16)), (cx, int(S * 0.08))], fill=INK, width=w)
    d.ellipse((cx - 26, int(S * 0.045), cx + 26, int(S * 0.045) + 52),
              fill=CYAN, outline=INK, width=w)

    # Head — big rounded dome (most of the body: he's basically a walking eye)
    head = (int(S * 0.16), int(S * 0.16), int(S * 0.84), int(S * 0.62))
    rr(d, head, r=int(S * 0.16), fill=BODY, outline=INK, width=w)

    # Face plate — dark window holding the lens
    plate = (int(S * 0.24), int(S * 0.225), int(S * 0.76), int(S * 0.555))
    rr(d, plate, r=int(S * 0.11), fill=(22, 28, 40, 255), outline=INK, width=w)

    # The lens eye (family signature: blue iris, dark core, white glint)
    ecx, ecy = cx, int(S * 0.39)
    er = int(S * 0.115)
    d.ellipse((ecx - er, ecy - er, ecx + er, ecy + er), fill=IRIS, outline=INK, width=w)
    cr = int(er * 0.55)
    d.ellipse((ecx - cr, ecy - cr, ecx + cr, ecy + cr), fill=CORE)
    gr = int(er * 0.22)
    d.ellipse((ecx + int(er * 0.30) - gr, ecy - int(er * 0.42) - gr,
               ecx + int(er * 0.30) + gr, ecy - int(er * 0.42) + gr),
              fill=(255, 255, 255, 235))
    # Cyan scan line crossing the plate through the eye
    lh = S // 52
    rr(d, (int(S * 0.26), ecy - lh // 2, int(S * 0.74), ecy + lh // 2),
       r=lh // 2, fill=CYAN)

    # Side "ears" (sensor pods)
    for ex in (int(S * 0.105), int(S * 0.835)):
        rr(d, (ex, int(S * 0.33), ex + int(S * 0.06), int(S * 0.46)),
           r=int(S * 0.025), fill=BODY_SHADE, outline=INK, width=w)

    # Body — small rounded box under the head
    body = (int(S * 0.30), int(S * 0.635), int(S * 0.70), int(S * 0.84))
    rr(d, body, r=int(S * 0.07), fill=BODY, outline=INK, width=w)
    # Chest light: tiny green "raw extract ready" dot + document slot
    d.ellipse((cx - 22, int(S * 0.665), cx + 22, int(S * 0.665) + 44),
              fill=(80, 220, 130, 255), outline=INK, width=w // 2)
    rr(d, (int(S * 0.38), int(S * 0.745), int(S * 0.62), int(S * 0.775)),
       r=10, fill=(22, 28, 40, 255))

    # Arms — simple rounded stubs, one waving
    d.line([(int(S * 0.30), int(S * 0.70)), (int(S * 0.20), int(S * 0.76))],
           fill=INK, width=int(S * 0.035))
    d.line([(int(S * 0.70), int(S * 0.70)), (int(S * 0.81), int(S * 0.60))],
           fill=INK, width=int(S * 0.035))
    for hx, hy in ((int(S * 0.20), int(S * 0.76)), (int(S * 0.81), int(S * 0.60))):
        r = int(S * 0.030)
        d.ellipse((hx - r, hy - r, hx + r, hy + r), fill=BODY_SHADE, outline=INK, width=w // 2)

    # Feet — two little rounded pads
    for fx in (int(S * 0.36), int(S * 0.56)):
        rr(d, (fx, int(S * 0.835), fx + int(S * 0.09), int(S * 0.885)),
           r=int(S * 0.02), fill=BODY_SHADE, outline=INK, width=w // 2)

    return img.resize((512, 512), Image.LANCZOS)


def wizard_images(mascot: Image.Image) -> None:
    """Inno wizard art: dark brand panel with Scout centered (BMP required)."""
    stage = ROOT / "build" / "stage"
    stage.mkdir(parents=True, exist_ok=True)

    panel = Image.new("RGB", (164, 314), (17, 21, 30))
    pd = ImageDraw.Draw(panel)
    for y in range(314):  # subtle vertical blend, same palette as the icon badge
        t = y / 314
        pd.line([(0, y), (164, y)],
                fill=(int(28 - 11 * t), int(34 - 13 * t), int(46 - 16 * t)))
    m = mascot.resize((132, 132), Image.LANCZOS)
    panel.paste(m, ((164 - 132) // 2, 60), m)
    pd.line([(28, 230), (136, 230)], fill=(0, 220, 255), width=3)
    panel.save(stage / "wizard.bmp")

    small = Image.new("RGB", (55, 55), (17, 21, 30))
    icon = Image.open(ROOT / "assets" / "icon.png").resize((47, 47), Image.LANCZOS)
    small.paste(icon, (4, 4), icon)
    small.save(stage / "wizard_small.bmp")


def main() -> None:
    mascot = draw_scout()
    (ROOT / "assets").mkdir(exist_ok=True)
    mascot.save(ROOT / "assets" / "mascot.png")
    wizard_images(mascot)
    print("mascot + wizard images written")


if __name__ == "__main__":
    sys.exit(main())
