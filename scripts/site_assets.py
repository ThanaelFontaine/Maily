"""Regenerate the product page assets in site/ from the repository sources.

Copies the screenshots of docs/images into site/assets (theme-dedsec.png is
published as theme-zeroday.png until the image itself is renamed), then
derives the favicons and the 1200x630 Open Graph image from
packaging/maily.png and docs/images/classic-light.png.

Usage: uv run --group build python scripts/site_assets.py
"""

from __future__ import annotations

import shutil
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
ASSETS = SITE / "assets"
RENAMED = {"theme-dedsec.png": "theme-zeroday.png"}


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Return Helvetica Neue on macOS, or Pillow's default font elsewhere."""
    candidate = Path("/System/Library/Fonts/HelveticaNeue.ttc")
    if candidate.exists():
        return ImageFont.truetype(str(candidate), size, index=1 if bold else 0)
    return ImageFont.load_default(size)


def copy_screenshots() -> None:
    for image in sorted((ROOT / "docs" / "images").glob("*.png")):
        shutil.copyfile(image, ASSETS / RENAMED.get(image.name, image.name))


def icons(source: Image.Image) -> None:
    for size, name in [
        (32, "assets/favicon-32.png"),
        (96, "assets/logo-96.png"),
        (180, "apple-touch-icon.png"),
        (192, "assets/icon-192.png"),
        (512, "assets/icon-512.png"),
    ]:
        source.resize((size, size), Image.LANCZOS).save(SITE / name, optimize=True)
    source.resize((64, 64), Image.LANCZOS).save(
        SITE / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64)]
    )


def og_image(source: Image.Image) -> None:
    width, height = 1200, 630
    og = Image.new("RGB", (width, height), "#f6f8fc")
    draw = ImageDraw.Draw(og)
    logo = source.resize((96, 96), Image.LANCZOS)
    og.paste(logo, (72, 72), logo)
    draw.text((188, 88), "Maily", font=font(60, True), fill="#1f1f1f")
    y = 206
    for line in ["Every mailbox", "in one app.", "Your AI assistant", "in all of them."]:
        draw.text((72, y), line, font=font(46, True), fill="#1f1f1f")
        y += 58
    draw.text((72, y + 24), "Free, open source mail app for macOS", font=font(28), fill="#444746")
    draw.text((72, y + 62), "with a local MCP server. Gmail + IMAP.", font=font(28), fill="#444746")
    shot = Image.open(ROOT / "docs" / "images" / "classic-light.png").convert("RGB")
    shot_w = 560
    shot_h = int(shot.height * shot_w / shot.width)
    shot = shot.resize((shot_w, shot_h), Image.LANCZOS)
    x0, y0 = 600, 150
    mask = Image.new("L", (shot_w, shot_h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, shot_w - 1, shot_h - 1), radius=14, fill=255)
    draw.rounded_rectangle((x0 - 1, y0 - 1, x0 + shot_w, y0 + shot_h), radius=15, outline="#e1e3e1", width=2)
    og.paste(shot, (x0, y0), mask)
    draw.rectangle((0, height - 10, width, height), fill="#1a73e8")
    og.save(ASSETS / "og-image.png", optimize=True)


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    copy_screenshots()
    source = Image.open(ROOT / "packaging" / "maily.png").convert("RGBA")
    icons(source)
    og_image(source)
    print(f"Assets written to {ASSETS.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
