"""Regenerate the product page assets in site/ from the repository sources.

1. Captures the screenshots of the app at 2x (2560x1600 pixels for a 1280x800
   window) on the fictitious data of scripts/demo.py, in a temporary folder, with
   headless Chromium. The real data folder and the real secrets are never used.
2. Encodes each screenshot for the page in site/assets/shots/: WebP and AVIF at
   640, 1280 and 2560 pixels wide (plus 1920 for the hero images), so the browser
   picks a sharp 1x or 2x file for the space it has.
3. Derives the favicons from packaging/maily.png and the 1200x630 Open Graph image.

Usage, from the repository root:
  uv run --group build --with playwright python scripts/site_assets.py
  uv run --group build python scripts/site_assets.py --from DIR   # reuse 2560x1600 captures

The first run may need the browser: uv run --with playwright playwright install chromium
"""

from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
ASSETS = SITE / "assets"
SHOTS = ASSETS / "shots"

VIEWPORT = {"width": 1280, "height": 800}
SCALE = 2
WIDTHS = (640, 1280, 2560)
HERO_WIDTHS = (640, 1280, 1920, 2560)
HERO = {"classic-light", "classic-dark"}
WEBP_QUALITY = 88
AVIF_QUALITY = 72

NAMES = (
    "classic-light", "classic-dark", "theme-aero", "theme-glass", "theme-zeroday",
    "remote-images-blocked", "composer",
    "settings-appearance", "settings-language", "settings-privacy", "settings-accounts",
)

# Stands in for the blurred desktop that macOS shows behind the Glassmorphism theme.
GLASS_BACKDROP = (
    "html{background:radial-gradient(120% 90% at 20% 15%,#5b4b9a 0%,transparent 55%),"
    "radial-gradient(90% 80% at 85% 80%,#1f6f8b 0%,transparent 60%),"
    "linear-gradient(135deg,#2b2f4a,#1a2233 60%,#22303a)}"
)


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Return Helvetica Neue on macOS, or Pillow's default font elsewhere."""
    candidate = Path("/System/Library/Fonts/HelveticaNeue.ttc")
    if candidate.exists():
        return ImageFont.truetype(str(candidate), size, index=1 if bold else 0)
    return ImageFont.load_default(size)


# Capture ---------------------------------------------------------------------


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class Demo:
    """scripts/demo.py on a fresh temporary data folder."""

    def __enter__(self) -> "Demo":
        self.dir = tempfile.mkdtemp(prefix="maily-site-demo-")
        port = free_port()
        env = {**os.environ, "MAILY_NO_BIOMETRIC": "1",
               "PYTHON_KEYRING_BACKEND": "keyring.backends.null.Keyring"}
        env.pop("MAILY_DATA_DIR", None)
        self.proc = subprocess.Popen(
            [sys.executable, "scripts/demo.py", "--port", str(port), "--data-dir", self.dir],
            cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.url = f"http://127.0.0.1:{port}/"
        for _ in range(150):
            try:
                urllib.request.urlopen(self.url + "health", timeout=1)
                return self
            except OSError:
                time.sleep(0.2)
        self.proc.kill()
        raise RuntimeError("the demo server did not start")

    def __exit__(self, *exc: object) -> None:
        self.proc.terminate()
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill()


def capture(out: Path) -> None:
    from playwright.sync_api import sync_playwright

    def page_for(browser, demo, scheme="light", prefs=None):
        ctx = browser.new_context(viewport=VIEWPORT, device_scale_factor=SCALE,
                                  locale="en-US", color_scheme=scheme)
        page = ctx.new_page()
        page.goto(demo.url)
        page.wait_for_selector(".li")
        page.evaluate("""async (p) => {
          await fetch('/prefs', {method: 'POST', headers: {Authorization: 'Bearer ' + window.MAILY_TOKEN,
            'Content-Type': 'application/json'}, body: JSON.stringify(p)});
        }""", {"language": "en", **(prefs or {})})
        page.reload()
        page.wait_for_selector(".li")
        page.wait_for_timeout(300)
        return ctx, page

    def open_first(page):
        page.click(".li >> nth=0")
        page.wait_for_selector(".read-head")
        page.wait_for_timeout(500)

    def shot(page, name):
        page.mouse.move(1, 1)
        page.wait_for_timeout(400)
        page.screenshot(path=str(out / f"{name}.png"))

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for scheme, name in (("light", "classic-light"), ("dark", "classic-dark")):
            with Demo() as demo:
                ctx, page = page_for(browser, demo, scheme)
                open_first(page)
                shot(page, name)
                ctx.close()
        for theme in ("aero", "glass", "zeroday"):
            with Demo() as demo:
                ctx, page = page_for(browser, demo, "dark" if theme == "glass" else "light",
                                     {"theme": theme})
                if theme == "glass":
                    page.add_style_tag(content=GLASS_BACKDROP)
                open_first(page)
                shot(page, f"theme-{theme}")
                ctx.close()
        with Demo() as demo:
            ctx, page = page_for(browser, demo)
            page.click(".cat >> nth=1")  # Promotions: the newsletter with remote images
            page.wait_for_timeout(400)
            open_first(page)
            shot(page, "remote-images-blocked")
            page.click("#replybtn")
            page.wait_for_timeout(200)
            page.fill("#c-to", "camille@example.com")
            page.fill("#c-subject", "Re: Thursday's progress meeting")
            page.fill("#c-body", "Thanks Camille, I will review the FAQ tomorrow.")
            shot(page, "composer")
            page.click("#c-cancel")
            page.click(".cat >> nth=0")
            page.wait_for_timeout(300)
            open_first(page)
            page.click("#settingsbtn")
            for pane in ("appearance", "language", "privacy", "accounts"):
                page.click(f"#tab-{pane}")
                page.wait_for_timeout(250)
                shot(page, f"settings-{pane}")
            ctx.close()
        browser.close()


# Encoding --------------------------------------------------------------------


def encode(source_dir: Path) -> None:
    SHOTS.mkdir(parents=True, exist_ok=True)
    for old in SHOTS.glob("*"):
        old.unlink()
    for name in NAMES:
        master = Image.open(source_dir / f"{name}.png").convert("RGB")
        expected = (VIEWPORT["width"] * SCALE, VIEWPORT["height"] * SCALE)
        if master.size != expected:
            raise SystemExit(f"{name}.png is {master.size}, expected {expected}")
        for width in HERO_WIDTHS if name in HERO else WIDTHS:
            height = round(master.height * width / master.width)
            image = master if width == master.width else master.resize((width, height), Image.LANCZOS)
            image.save(SHOTS / f"{name}-{width}.webp", quality=WEBP_QUALITY, method=6)
            image.save(SHOTS / f"{name}-{width}.avif", quality=AVIF_QUALITY, speed=4)


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


def og_image(source: Image.Image, screenshot: Path) -> None:
    width, height = 1200, 630
    og = Image.new("RGB", (width, height), "#f6f8fc")
    draw = ImageDraw.Draw(og)
    logo = source.resize((96, 96), Image.LANCZOS)
    og.paste(logo, (72, 72), logo)
    draw.text((188, 88), "Maily", font=font(60, True), fill="#1f1f1f")
    y = 206
    for line in ["All your mailboxes.", "Every assistant.", "One connection."]:
        draw.text((72, y), line, font=font(46, True), fill="#1f1f1f")
        y += 58
    draw.text((72, y + 24), "The mail bridge for your AI assistants:", font=font(28), fill="#444746")
    draw.text((72, y + 62), "Gmail + IMAP, one local MCP server.", font=font(28), fill="#444746")
    shot = Image.open(screenshot).convert("RGB")
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
    parser = argparse.ArgumentParser(description="Regenerate the product page assets.")
    parser.add_argument("--from", dest="source", type=Path,
                        help="folder of existing 2560x1600 captures (default: capture them now)")
    args = parser.parse_args()
    ASSETS.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="maily-site-shots-") as tmp:
        source_dir = args.source or Path(tmp)
        if args.source is None:
            capture(source_dir)
        encode(source_dir)
        logo = Image.open(ROOT / "packaging" / "maily.png").convert("RGBA")
        icons(logo)
        og_image(logo, source_dir / "classic-light.png")
    total = sum(f.stat().st_size for f in SHOTS.iterdir())
    print(f"Assets written to {ASSETS.relative_to(ROOT)} ({total // 1024} KB of screenshots)")


if __name__ == "__main__":
    main()
