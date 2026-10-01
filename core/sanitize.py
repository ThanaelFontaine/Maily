from __future__ import annotations
import nh3

_RESOURCE_ATTRS = {"src", "background", "poster", "srcset"}

# Inline CSS properties allowed (faithful rendering of mail) WITHOUT bringing
# back an attack surface: no position (breakout), no background/-image
# (url() = remote content / tracking), no behavior/expression.
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

# Allowed attributes = nh3 defaults + style + mail layout attributes.
_ATTRS = {tag: set(attrs) for tag, attrs in nh3.ALLOWED_ATTRIBUTES.items()}
_ATTRS.setdefault("*", set()).add("style")
_ATTRS.setdefault("img", set()).update({"src", "alt", "width", "height", "title"})
_ATTRS.setdefault("table", set()).update({"width", "cellpadding", "cellspacing", "border", "align", "bgcolor"})
_ATTRS.setdefault("td", set()).update({"width", "height", "align", "valign", "bgcolor", "colspan", "rowspan"})
_ATTRS.setdefault("th", set()).update({"width", "height", "align", "valign", "bgcolor", "colspan", "rowspan"})
_ATTRS.setdefault("tr", set()).update({"bgcolor", "align", "valign"})
_ATTRS.setdefault("font", set()).update({"color", "face", "size"})


def sanitize_html_report(html: str, allow_remote: bool = False) -> tuple[str, int]:
    """Cleans the HTML of a message and counts the blocked remote resources.

    Returns (clean_html, number_of_remote_resources_removed). The counter lets
    the interface offer "Show images" only when something was really blocked.
    """
    if not html:
        return "", 0
    blocked = 0

    def attr_filter(tag: str, attr: str, value: str):
        nonlocal blocked
        low = value.strip().lower()
        # Links: never data:/javascript:/vbscript: (phishing/XSS)
        if attr == "href" and low.startswith(("data:", "javascript:", "vbscript:")):
            return None
        # Resources (images...): when remote content is blocked, allow ONLY local ones
        # (cid: embedded images, data: inline images). Blocks http(s), //host and relative URLs.
        if attr in _RESOURCE_ATTRS and not allow_remote:
            if not low.startswith(("cid:", "data:")):
                if low:
                    blocked += 1
                return None
        return value

    cleaned = nh3.clean(
        html,
        attributes=_ATTRS,
        filter_style_properties=_STYLE_PROPS,
        url_schemes={"http", "https", "mailto", "cid", "data"},
        attribute_filter=attr_filter,
        link_rel="noopener noreferrer nofollow",
    )
    return cleaned, blocked


def sanitize_html(html: str, allow_remote: bool = False) -> str:
    return sanitize_html_report(html, allow_remote=allow_remote)[0]
