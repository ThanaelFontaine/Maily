"""Parses a raw RFC 822 message (IMAP) into the same fields as Gmail.

Produces a dict of fields accepted by `store.upsert_message` (keys of
`_MESSAGE_COLS`) + a list of attachments with an `imap:{i}` locator that lets
the part be extracted again later (`extract_part`).

Standard library only (`email` with the `default` policy: decoded headers and
charsets).
"""
from __future__ import annotations
import email
import email.policy
import email.utils
import json


def _msg(raw: bytes):
    return email.message_from_bytes(raw, policy=email.policy.default)


def _iter_attachment_parts(msg):
    """Parts treated as attachments (files + inline parts with a CID), in
    order: the same enumeration is used for parsing and for extraction."""
    for part in msg.walk():
        if part.is_multipart():
            continue
        filename = part.get_filename()
        cd = part.get_content_disposition()
        cid = part.get("Content-ID")
        if cd == "attachment" or filename is not None or (cd == "inline" and cid):
            yield part


def _bodies(msg):
    text = html = None
    if msg.is_multipart():
        for part in msg.walk():
            if part.is_multipart():
                continue
            if part.get_content_disposition() == "attachment" or part.get_filename():
                continue
            ctype = part.get_content_type()
            if ctype == "text/plain" and text is None:
                text = part.get_content()
            elif ctype == "text/html" and html is None:
                html = part.get_content()
    else:
        if msg.get_content_type() == "text/html":
            html = msg.get_content()
        else:
            text = msg.get_content()
    return text, html


def _internal_date_ms(msg):
    raw_date = msg.get("Date")
    if not raw_date:
        return None
    try:
        dt = email.utils.parsedate_to_datetime(raw_date)
        return int(dt.timestamp() * 1000)
    except (TypeError, ValueError):
        return None


def _snippet(text, html):
    base = (text or "").strip()
    if not base and html:
        # very simple fallback: strip the tags to get a preview
        import re
        base = re.sub(r"<[^>]+>", " ", html)
    base = " ".join(base.split())
    return base[:200] or None


def parse_rfc822(raw: bytes) -> tuple[dict, list[dict]]:
    msg = _msg(raw)
    text, html = _bodies(msg)
    attachments = []
    for i, part in enumerate(_iter_attachment_parts(msg)):
        payload = part.get_payload(decode=True) or b""
        cid = (part.get("Content-ID") or "").strip("<>") or None
        attachments.append({
            "filename": part.get_filename() or "attachment",
            "mime_type": part.get_content_type(),
            "size": len(payload),
            "gmail_attachment_id": f"imap:{i}",
            "content_id": cid,
        })
    msg_id = msg.get("Message-ID")
    fields = {
        "thread_id": msg_id,                 # no IMAP threads: each message is its own thread
        "rfc822_message_id": msg_id,
        "direction": "in",
        "addr_from": msg.get("From"),
        "addr_to": msg.get("To"),
        "addr_cc": msg.get("Cc"),
        "addr_bcc": msg.get("Bcc"),
        "subject": msg.get("Subject"),
        "snippet": _snippet(text, html),
        "body_text": text,
        "body_html": html,
        "internal_date": _internal_date_ms(msg),
        "has_attachments": 1 if attachments else 0,
    }
    # str() on the headers (Header objects with policy.default) to get plain text.
    for k in ("addr_from", "addr_to", "addr_cc", "addr_bcc", "subject",
              "thread_id", "rfc822_message_id"):
        if fields[k] is not None:
            fields[k] = str(fields[k])
    return fields, attachments


def extract_part(raw: bytes, locator: str) -> tuple[bytes, str, str]:
    """Returns (bytes, mime, filename) of the attachment located by
    `imap:{index}` (same enumeration as parse_rfc822)."""
    try:
        index = int(str(locator).split(":")[-1])
    except (TypeError, ValueError):
        raise ValueError(f"invalid attachment locator: {locator!r}")
    msg = _msg(raw)
    for i, part in enumerate(_iter_attachment_parts(msg)):
        if i == index:
            data = part.get_payload(decode=True) or b""
            return data, part.get_content_type(), part.get_filename() or "attachment"
    raise ValueError(f"attachment not found: {locator!r}")
