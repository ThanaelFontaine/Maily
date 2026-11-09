"""Parses a raw RFC 822 message (IMAP) into the same fields as Gmail.

Produces a dict of fields accepted by `store.upsert_message` (keys of
`_MESSAGE_COLS`) + a list of attachments with an `imap:{i}` locator that lets
the part be extracted again later (`extract_part`).

Standard library only (`email` with the `default` policy: decoded headers and
charsets).
"""
from __future__ import annotations
import email
import email.header
import email.parser
import email.policy
import email.utils
import json
import logging

log = logging.getLogger("maily.rfc822")

# A message the parser cannot read (broken charset, absurd nesting) is stored as a
# placeholder card carrying this local label, so that a future fix can find it and
# import it again, instead of blocking the whole sync.
UNREADABLE_LABEL = "MAILY_UNREADABLE"
UNREADABLE_BODY = "Maily could not read this message. Open it with your mail provider."


def _msg(raw: bytes):
    return email.message_from_bytes(raw, policy=email.policy.default)


def _content(part) -> str:
    """Decoded text of a text part. An unknown or invalid charset falls back to UTF-8
    with replacement characters, so the message is shown instead of failing."""
    try:
        return part.get_content()
    except (LookupError, UnicodeError):
        payload = part.get_payload(decode=True) or b""
        return payload.decode("utf-8", errors="replace")


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
                text = _content(part)
            elif ctype == "text/html" and html is None:
                html = _content(part)
    else:
        if msg.get_content_type() == "text/html":
            html = _content(msg)
        else:
            text = _content(msg)
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


def _plain_header(value):
    """Header as clean text, whatever its encoding (no surrogates, never raises)."""
    if value is None:
        return None
    try:
        text = str(email.header.make_header(email.header.decode_header(str(value))))
    except Exception:
        text = str(value)
    return text.encode("utf-8", errors="replace").decode("utf-8")


def parse_headers_only(raw: bytes) -> dict:
    """Fallback card for a message `parse_rfc822` cannot read: the headers only (read
    with the permissive `compat32` policy, which never recurses into the body), a
    fixed placeholder body, no attachment."""
    msg = email.parser.BytesParser(policy=email.policy.compat32).parsebytes(
        raw, headersonly=True)
    msg_id = _plain_header(msg.get("Message-ID"))
    return {
        "thread_id": msg_id,
        "rfc822_message_id": msg_id,
        "direction": "in",
        "addr_from": _plain_header(msg.get("From")),
        "addr_to": _plain_header(msg.get("To")),
        "addr_cc": _plain_header(msg.get("Cc")),
        "addr_bcc": _plain_header(msg.get("Bcc")),
        "subject": _plain_header(msg.get("Subject")),
        "snippet": UNREADABLE_BODY,
        "body_text": UNREADABLE_BODY,
        "body_html": None,
        "internal_date": _internal_date_ms(msg),
        "has_attachments": 0,
    }


def parse_rfc822_safe(raw: bytes) -> tuple[dict, list[dict], bool]:
    """`parse_rfc822` that survives a malformed message: (fields, attachments, readable).
    On failure, the fields are the headers-only fallback card and `readable` is False.
    Only the analysis is guarded; the caller keeps network errors out of this."""
    try:
        fields, atts = parse_rfc822(raw)
        return fields, atts, True
    except Exception as e:  # RecursionError, LookupError, ValueError... any parser failure
        log.warning("unreadable message stored as a placeholder (%s)", type(e).__name__)
    try:
        fields = parse_headers_only(raw)
    except Exception:
        fields = {"direction": "in", "snippet": UNREADABLE_BODY,
                  "body_text": UNREADABLE_BODY, "has_attachments": 0}
    return fields, [], False


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
