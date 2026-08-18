"""Genere le logo/icone de Maily (enveloppe sur pastille violette dégradée)
en PNG 1024. Voir scripts/make_icns.sh pour la conversion en .icns macOS."""
from __future__ import annotations
import pathlib
from PIL import Image, ImageDraw

S = 1024
OUT = pathlib.Path(__file__).resolve().parent / "maily.png"


def lerp(a, b, t):
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def rounded_mask(size, radius):
    m = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(m)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    return m


def main():
    # Fond : dégradé vertical violet (famille accent du thème Verre)
    top, bot = (0x9D, 0x86, 0xFF), (0x63, 0x49, 0xE8)
    grad = Image.new("RGB", (S, S))
    gd = ImageDraw.Draw(grad)
    for y in range(S):
        gd.line([(0, y), (S, y)], fill=lerp(top, bot, y / (S - 1)))

    icon = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    icon.paste(grad, (0, 0), rounded_mask(S, 228))  # squircle-ish

    d = ImageDraw.Draw(icon)

    # Reflet doux en haut
    hi = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    hd = ImageDraw.Draw(hi)
    hd.rounded_rectangle([60, 40, S - 60, S // 2], radius=200, fill=(255, 255, 255, 26))
    icon.alpha_composite(Image.composite(hi, Image.new("RGBA", (S, S), (0, 0, 0, 0)),
                                         rounded_mask(S, 228)))

    # Corps de l'enveloppe (blanc, coins arrondis) + ombre portée douce
    bx0, by0, bx1, by1 = 258, 356, 766, 700
    sh = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle([bx0, by0 + 16, bx1, by1 + 16], radius=54,
                                         fill=(40, 20, 90, 90))
    icon.alpha_composite(sh)
    d.rounded_rectangle([bx0, by0, bx1, by1], radius=54, fill=(255, 255, 255, 255))

    # Rabat en "V" (trait violet, jonctions arrondies)
    purple = (0x6D, 0x5E, 0xF6, 255)
    apex = (S // 2, by0 + 210)
    p_left = (bx0 + 46, by0 + 40)
    p_right = (bx1 - 46, by0 + 40)
    d.line([p_left, apex, p_right], fill=purple, width=46, joint="curve")
    for p in (p_left, apex, p_right):
        d.ellipse([p[0] - 23, p[1] - 23, p[0] + 23, p[1] + 23], fill=purple)

    # Badge "non lu" (accent) en haut a droite de l'enveloppe
    bd = (bx1 - 40, by0 - 40)
    d.ellipse([bd[0] - 62, bd[1] - 62, bd[0] + 62, bd[1] + 62], fill=(255, 255, 255, 255))
    d.ellipse([bd[0] - 44, bd[1] - 44, bd[0] + 44, bd[1] + 44], fill=(0xFF, 0x4D, 0x8D, 255))

    icon.save(OUT)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
