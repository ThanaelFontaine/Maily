from __future__ import annotations
import nh3

_RESOURCE_ATTRS = {"src", "background", "poster", "srcset"}


def sanitize_html(html: str, allow_remote: bool = False) -> str:
    if not html:
        return ""

    def attr_filter(tag: str, attr: str, value: str):
        if attr in _RESOURCE_ATTRS:
            low = value.strip().lower()
            if low.startswith(("http://", "https://")) and not allow_remote:
                return None
        return value

    return nh3.clean(
        html,
        url_schemes={"http", "https", "mailto", "cid", "data"},
        attribute_filter=attr_filter,
        link_rel="noopener noreferrer nofollow",
    )
