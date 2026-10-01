"""Draws the background of the macOS disk image (Maily-X.Y.Z-macos-arm64.dmg).

Usage: python packaging/make_dmg_background.py OUT_DIR
Writes OUT_DIR/background.png (640 x 440 points) and OUT_DIR/background@2x.png
(1280 x 880, Retina). The window shows about 640 x 400 of it (its 430 point
frame includes the title bar); the extra height only makes sure that no bare
strip shows under the picture whatever the title bar height. dmgbuild finds the @2x file
next to the 1x one and combines both into one HiDPI TIFF (tiffutil).

The layout matches packaging/dmg_settings.py: the Maily icon on the left, the
Applications shortcut on the right, an arrow between them and one sentence
that says what to do.

The base color has a relative luminance close to 0.18, so that the icon
labels Finder draws under each icon stay legible in both appearances: black
labels (light mode) and white labels (dark mode) both reach a contrast of
about 4.5:1 on it.
"""
from __future__ import annotations

import pathlib
import sys

from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 640, 440            # picture size, in points (content: 640 x 400)
APP_X, LINK_X, ICON_Y = 160, 480, 200  # icon centers (see dmg_settings.py)
ICON_SIZE = 128

TOP = (0x68, 0x7A, 0xB0)            # gradient, top
BOTTOM = (0x58, 0x6A, 0xA0)         # gradient, bottom (around #5F74A8 at the labels)
INK = (0xFF, 0xFF, 0xFF)
INK_SOFT = (0xFF, 0xFF, 0xFF, 0xD9)

TITLE = "Drag Maily to Applications"
SUBTITLE = "Then open Maily from your Applications folder."
# Maily is not signed by Apple: the first launch needs one approval.
NOTE = ("If macOS blocks the first launch: System Settings > Privacy & Security > Open Anyway",)

_FONTS = [
    # macOS system fonts (the image is only built on a Mac).
    ("/System/Library/Fonts/HelveticaNeue.ttc", 1, 0),   # bold, regular
    ("/System/Library/Fonts/Helvetica.ttc", 1, 0),
]


def _fonts(scale: int):
    for path, bold, regular in _FONTS:
        if pathlib.Path(path).exists():
            try:
                return (ImageFont.truetype(path, 26 * scale, index=bold),
                        ImageFont.truetype(path, 15 * scale, index=regular),
                        ImageFont.truetype(path, 12 * scale, index=regular))
            except OSError:
                continue
    # Pillow's bundled scalable font (Pillow >= 10.1).
    return (ImageFont.load_default(26 * scale), ImageFont.load_default(15 * scale),
            ImageFont.load_default(12 * scale))


def draw(scale: int) -> Image.Image:
    w, h = WIDTH * scale, HEIGHT * scale
    img = Image.new("RGB", (w, h))
    px = ImageDraw.Draw(img)
    for y in range(h):
        t = y / (h - 1)
        px.line([(0, y), (w, y)], fill=tuple(round(a + (b - a) * t) for a, b in zip(TOP, BOTTOM)))

    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    title_font, sub_font, note_font = _fonts(scale)
    d.text((w / 2, 58 * scale), TITLE, font=title_font, fill=INK, anchor="mm")
    d.text((w / 2, 92 * scale), SUBTITLE, font=sub_font, fill=INK_SOFT, anchor="mm")

    # Arrow from the Maily icon to the Applications shortcut.
    half = ICON_SIZE // 2
    x0 = (APP_X + half + 22) * scale
    x1 = (LINK_X - half - 22) * scale
    y = ICON_Y * scale
    stroke = 5 * scale
    head = 16 * scale
    d.line([(x0, y), (x1 - head + 2 * scale, y)], fill=INK, width=stroke)
    d.polygon([(x1, y), (x1 - head, y - head * 0.75), (x1 - head, y + head * 0.75)], fill=INK)

    for i, line in enumerate(NOTE):
        d.text((w / 2, (356 + 18 * i) * scale), line, font=note_font, fill=INK_SOFT, anchor="mm")

    img.paste(layer, (0, 0), layer)
    return img


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: make_dmg_background.py OUT_DIR", file=sys.stderr)
        return 2
    out = pathlib.Path(argv[0])
    out.mkdir(parents=True, exist_ok=True)
    draw(1).save(out / "background.png", dpi=(72, 72))
    draw(2).save(out / "background@2x.png", dpi=(144, 144))
    print(f"{out / 'background.png'} and {out / 'background@2x.png'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
