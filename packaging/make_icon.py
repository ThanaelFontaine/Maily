"""Maily logo/icon: a "liquid glass" squircle with a subtle aqua/lavender tint
(Frutiger Aero), with a minimal envelope. Renders a 1024 PNG; see
scripts/build_macos.sh for the .icns."""
from __future__ import annotations
import pathlib
from PIL import Image, ImageDraw, ImageFilter

S = 1024
R = 236  # squircle radius
OUT = pathlib.Path(__file__).resolve().parent / "maily.png"


def lerp(a, b, t):
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def squircle_mask():
    m = Image.new("L", (S, S), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, S - 1, S - 1], radius=R, fill=255)
    return m


def clip(layer, mask):
    out = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    out.paste(layer, (0, 0), mask)
    return out


def main():
    mask = squircle_mask()

    # Background: soft vertical gradient from aqua to lavender (subtle Frutiger Aero).
    top, bot = (214, 236, 255), (232, 227, 251)
    grad = Image.new("RGB", (S, S))
    gd = ImageDraw.Draw(grad)
    for y in range(S):
        gd.line([(0, y), (S, y)], fill=lerp(top, bot, y / (S - 1)))
    icon = clip(grad.convert("RGBA"), mask)

    # Depth: light dark vignette at the bottom (thick glass).
    vg = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(vg).ellipse([-160, S - 360, S + 160, S + 260], fill=(60, 70, 120, 60))
    icon.alpha_composite(clip(vg.filter(ImageFilter.GaussianBlur(80)), mask))

    # Sheen: large white highlight at the top (glass bubble).
    sh = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(sh).ellipse([-120, -300, S + 120, 430], fill=(255, 255, 255, 135))
    icon.alpha_composite(clip(sh.filter(ImageFilter.GaussianBlur(55)), mask))

    # Bright rim along the top edge (glass light).
    rim = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(rim).rounded_rectangle([3, 3, S - 4, S - 4], radius=R - 2,
                                          outline=(255, 255, 255, 150), width=4)
    icon.alpha_composite(clip(rim, mask))

    d = ImageDraw.Draw(icon)

    # Soft shadow under the envelope.
    bx0, by0, bx1, by1 = 196, 340, 828, 724   # bigger envelope
    shadow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle([bx0, by0 + 24, bx1, by1 + 26], radius=66,
                                             fill=(70, 90, 150, 120))
    icon.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(24)))

    # Minimal envelope: translucent white + thin blue-grey rim.
    d.rounded_rectangle([bx0, by0, bx1, by1], radius=66,
                        fill=(255, 255, 255, 238), outline=(150, 172, 208, 170), width=3)

    # "V" flap (soft blue, rounded joints).
    blue = (108, 138, 190, 230)
    apex = (S // 2, by0 + 226)
    pl, pr = (bx0 + 56, by0 + 52), (bx1 - 56, by0 + 52)
    d.line([pl, apex, pr], fill=blue, width=36, joint="curve")
    for p in (pl, apex, pr):
        d.ellipse([p[0] - 18, p[1] - 18, p[0] + 18, p[1] + 18], fill=blue)

    # Glossy highlight on the top of the envelope.
    gloss = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(gloss).rounded_rectangle([bx0 + 18, by0 + 14, bx1 - 18, by0 + 112],
                                            radius=52, fill=(255, 255, 255, 90))
    icon.alpha_composite(gloss.filter(ImageFilter.GaussianBlur(11)))

    icon.save(OUT)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
