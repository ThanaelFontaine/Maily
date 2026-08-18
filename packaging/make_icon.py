"""Logo/icone Maily : squircle "liquid glass" (Apple) a teinte aqua/lavande
discrete (Frutiger Aero), avec une enveloppe minimale. Rend un PNG 1024 ;
voir scripts/build_macos.sh (ou make_icns) pour le .icns."""
from __future__ import annotations
import pathlib
from PIL import Image, ImageDraw, ImageFilter

S = 1024
R = 236  # rayon du squircle
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

    # Fond : degrade vertical doux aqua -> lavande (Frutiger Aero discret).
    top, bot = (214, 236, 255), (232, 227, 251)
    grad = Image.new("RGB", (S, S))
    gd = ImageDraw.Draw(grad)
    for y in range(S):
        gd.line([(0, y), (S, y)], fill=lerp(top, bot, y / (S - 1)))
    icon = clip(grad.convert("RGBA"), mask)

    # Profondeur : legere vignette sombre en bas (verre epais).
    vg = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(vg).ellipse([-160, S - 360, S + 160, S + 260], fill=(60, 70, 120, 60))
    icon.alpha_composite(clip(vg.filter(ImageFilter.GaussianBlur(80)), mask))

    # Sheen : grande brillance blanche en haut (bulle de verre).
    sh = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(sh).ellipse([-120, -300, S + 120, 430], fill=(255, 255, 255, 135))
    icon.alpha_composite(clip(sh.filter(ImageFilter.GaussianBlur(55)), mask))

    # Liseré lumineux sur le bord haut (lumiere Apple glass).
    rim = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(rim).rounded_rectangle([3, 3, S - 4, S - 4], radius=R - 2,
                                          outline=(255, 255, 255, 150), width=4)
    icon.alpha_composite(clip(rim, mask))

    d = ImageDraw.Draw(icon)

    # Ombre douce sous l'enveloppe.
    bx0, by0, bx1, by1 = 258, 372, 766, 690
    shadow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle([bx0, by0 + 20, bx1, by1 + 22], radius=58,
                                             fill=(70, 90, 150, 120))
    icon.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(22)))

    # Enveloppe minimale : blanc translucide + fin liseré bleu-gris.
    d.rounded_rectangle([bx0, by0, bx1, by1], radius=58,
                        fill=(255, 255, 255, 238), outline=(150, 172, 208, 170), width=3)

    # Rabat en "V" (bleu doux, jonctions arrondies).
    blue = (108, 138, 190, 230)
    apex = (S // 2, by0 + 186)
    pl, pr = (bx0 + 48, by0 + 44), (bx1 - 48, by0 + 44)
    d.line([pl, apex, pr], fill=blue, width=30, joint="curve")
    for p in (pl, apex, pr):
        d.ellipse([p[0] - 15, p[1] - 15, p[0] + 15, p[1] + 15], fill=blue)

    # Reflet glossy sur le haut de l'enveloppe.
    gloss = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(gloss).rounded_rectangle([bx0 + 16, by0 + 12, bx1 - 16, by0 + 96],
                                            radius=44, fill=(255, 255, 255, 90))
    icon.alpha_composite(gloss.filter(ImageFilter.GaussianBlur(10)))

    icon.save(OUT)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
