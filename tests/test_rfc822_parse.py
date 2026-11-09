from email.message import EmailMessage
from core.rfc822_parse import parse_rfc822, extract_part


def _sample() -> bytes:
    m = EmailMessage()
    m["From"] = "Alice <alice@example.net>"
    m["To"] = "bob@example.com"
    m["Cc"] = "carol@example.com"
    m["Subject"] = "Café meeting ☕"
    m["Message-ID"] = "<abc123@example.net>"
    m["Date"] = "Mon, 18 Aug 2025 10:30:00 +0200"
    m.set_content("Hello, this is the text body.")
    m.add_alternative("<p>Hello, <b>HTML</b>.</p>", subtype="html")
    m.add_attachment(b"%PDF-1.4 fake", maintype="application", subtype="pdf",
                     filename="invoice.pdf")
    return m.as_bytes()


def test_parse_headers_and_bodies():
    fields, atts = parse_rfc822(_sample())
    assert fields["addr_from"] == "Alice <alice@example.net>"
    assert fields["addr_to"] == "bob@example.com"
    assert fields["addr_cc"] == "carol@example.com"
    assert fields["subject"] == "Café meeting ☕"
    assert fields["rfc822_message_id"] == "<abc123@example.net>"
    assert fields["thread_id"] == "<abc123@example.net>"      # fil = message-id
    assert "text body" in fields["body_text"]
    assert "<b>HTML</b>" in fields["body_html"]
    assert fields["direction"] == "in"
    assert fields["has_attachments"] == 1
    # date -> epoch ms (2025-08-18 08:30 UTC)
    assert fields["internal_date"] == 1755505800000


def test_parse_attachments_metadata():
    _fields, atts = parse_rfc822(_sample())
    assert len(atts) == 1
    a = atts[0]
    assert a["filename"] == "invoice.pdf"
    assert a["mime_type"] == "application/pdf"
    assert a["size"] == len(b"%PDF-1.4 fake")
    assert a["gmail_attachment_id"] == "imap:0"


def test_extract_part_returns_bytes():
    raw = _sample()
    data, mime, filename = extract_part(raw, "imap:0")
    assert data == b"%PDF-1.4 fake"
    assert mime == "application/pdf"
    assert filename == "invoice.pdf"


def test_parse_plain_only():
    m = EmailMessage()
    m["From"] = "x@example.org"
    m["Subject"] = "Simple"
    m["Date"] = "Mon, 18 Aug 2025 10:30:00 +0200"
    m.set_content("just some text")
    fields, atts = parse_rfc822(m.as_bytes())
    assert fields["body_text"].strip() == "just some text"
    assert fields["has_attachments"] == 0
    assert atts == []


# --- MAIL-34 lot 2b: a malformed message never blocks the sync ---------------------

import pytest
from core.rfc822_parse import (
    parse_headers_only, parse_rfc822_safe, UNREADABLE_BODY)


def _bad_charset() -> bytes:
    return (b"From: a@example.net\r\nTo: me@example.net\r\nSubject: Bad charset\r\n"
            b"Message-ID: <bc@example.net>\r\nDate: Mon, 18 Aug 2025 10:30:00 +0200\r\n"
            b"Content-Type: text/plain; charset=x-nope\r\n\r\nh\xc3\xa9llo world\r\n")


def _deeply_nested(n=3000) -> bytes:
    head = (b"From: a@example.net\r\nTo: me@example.net\r\nSubject: Deep\r\n"
            b"Message-ID: <deep@example.net>\r\nDate: Mon, 18 Aug 2025 10:30:00 +0200\r\n")
    body = b"".join(b"Content-Type: multipart/mixed; boundary=b%d\r\n\r\n--b%d\r\n" % (i, i)
                    for i in range(n))
    return head + body


def test_unknown_charset_is_decoded_as_utf8_with_replacement():
    fields, _atts, readable = parse_rfc822_safe(_bad_charset())
    assert readable is True
    assert "world" in fields["body_text"]
    assert fields["subject"] == "Bad charset"


def test_unknown_charset_in_a_multipart_part_is_decoded_too():
    m = EmailMessage()
    m["Subject"] = "mp"
    m.set_content("plain")
    m.add_alternative("<p>html</p>", subtype="html")
    raw = m.as_bytes().replace(b'charset="utf-8"', b"charset=x-nope")
    fields, _atts, readable = parse_rfc822_safe(raw)
    assert readable is True
    assert "plain" in fields["body_text"] and "html" in fields["body_html"]


def test_invalid_bytes_for_a_known_charset_do_not_raise():
    raw = (b"Subject: s\r\nContent-Type: text/plain; charset=ascii\r\n"
           b"Content-Transfer-Encoding: 8bit\r\n\r\ncaf\xe9\r\n")
    fields, _atts, readable = parse_rfc822_safe(raw)
    assert readable is True
    assert fields["body_text"].startswith("caf")


def test_deeply_nested_multiparts_give_a_fallback_card():
    fields, atts, readable = parse_rfc822_safe(_deeply_nested())
    assert readable is False
    assert atts == []
    assert fields["body_text"] == UNREADABLE_BODY
    assert fields["body_html"] is None
    assert fields["has_attachments"] == 0
    assert fields["subject"] == "Deep"
    assert fields["addr_from"] == "a@example.net"
    assert fields["rfc822_message_id"] == "<deep@example.net>"
    assert fields["internal_date"] == 1755505800000


def test_fallback_log_line_has_no_content(caplog):
    with caplog.at_level("WARNING", logger="maily.rfc822"):
        parse_rfc822_safe(_deeply_nested())
    text = " ".join(r.getMessage() for r in caplog.records)
    assert "unreadable" in text
    assert "Deep" not in text and "example.net" not in text


def test_headers_only_decodes_encoded_words_and_never_raises():
    raw = (b"Subject: =?UTF-8?B?Q2Fmw6k=?=\r\nFrom: \xff\xfe <a@example.net>\r\n\r\nbody")
    f = parse_headers_only(raw)
    assert f["subject"] == "Café"
    f["addr_from"].encode("utf-8")        # no lone surrogate left


def test_garbage_that_even_the_header_reader_rejects_still_gives_a_card(monkeypatch):
    import core.rfc822_parse as mod
    monkeypatch.setattr(mod, "parse_rfc822", lambda raw: (_ for _ in ()).throw(ValueError("x")))
    monkeypatch.setattr(mod, "parse_headers_only", lambda raw: (_ for _ in ()).throw(ValueError("y")))
    fields, atts, readable = mod.parse_rfc822_safe(b"whatever")
    assert readable is False and atts == []
    assert fields["body_text"] == UNREADABLE_BODY


def test_attachment_enumeration_is_unchanged_for_an_ordinary_mail():
    raw = _sample()
    fields, atts, readable = parse_rfc822_safe(raw)
    assert readable is True
    assert [a["gmail_attachment_id"] for a in atts] == ["imap:0"]
    data, mime, _name = extract_part(raw, atts[0]["gmail_attachment_id"])
    assert data == b"%PDF-1.4 fake" and mime == "application/pdf"
