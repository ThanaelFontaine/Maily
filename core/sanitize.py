from __future__ import annotations
import nh3

_RESOURCE_ATTRS = {"src", "background", "poster", "srcset"}

# Proprietes CSS inline autorisees (fidelite des mails) SANS reintroduire de
# surface d'attaque : pas de position (breakout), pas de background/-image
# (url() = contenu distant / tracking), pas de behavior/expression.
_STYLE_PROPS = {
    "color", "background-color",
    "font", "font-size", "font-weight", "font-style", "font-family", "font-variant",
    "text-align", "text-decoration", "text-transform", "line-height", "letter-spacing",
    "padding", "padding-top", "padding-bottom", "padding-left", "padding-right",
    "margin", "margin-top", "margin-bottom", "margin-left", "margin-right",
    "border", "border-top", "border-bottom", "border-left", "border-right",
    "border-radius", "border-color", "border-width", "border-style", "border-collapse",
    "width", "max-width", "min-width", "height", "max-height", "min-height",
    "vertical-align", "white-space", "display",
}

# Attributs autorises = defauts nh3 + style + attributs de mise en page des mails.
_ATTRS = {tag: set(attrs) for tag, attrs in nh3.ALLOWED_ATTRIBUTES.items()}
_ATTRS.setdefault("*", set()).add("style")
_ATTRS.setdefault("img", set()).update({"src", "alt", "width", "height", "title"})
_ATTRS.setdefault("table", set()).update({"width", "cellpadding", "cellspacing", "border", "align", "bgcolor"})
_ATTRS.setdefault("td", set()).update({"width", "height", "align", "valign", "bgcolor", "colspan", "rowspan"})
_ATTRS.setdefault("th", set()).update({"width", "height", "align", "valign", "bgcolor", "colspan", "rowspan"})
_ATTRS.setdefault("tr", set()).update({"bgcolor", "align", "valign"})
_ATTRS.setdefault("font", set()).update({"color", "face", "size"})


def sanitize_html(html: str, allow_remote: bool = False) -> str:
    if not html:
        return ""

    def attr_filter(tag: str, attr: str, value: str):
        low = value.strip().lower()
        # Liens : jamais de data:/javascript:/vbscript: (phishing/XSS)
        if attr == "href" and low.startswith(("data:", "javascript:", "vbscript:")):
            return None
        # Ressources (images...) : si contenu distant bloque, n'autoriser QUE le local
        # (cid: images integrees, data: images inline). Bloque http(s), //host, et relatif.
        if attr in _RESOURCE_ATTRS and not allow_remote:
            if not low.startswith(("cid:", "data:")):
                return None
        return value

    return nh3.clean(
        html,
        attributes=_ATTRS,
        filter_style_properties=_STYLE_PROPS,
        url_schemes={"http", "https", "mailto", "cid", "data"},
        attribute_filter=attr_filter,
        link_rel="noopener noreferrer nofollow",
    )
