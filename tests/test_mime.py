import base64
from email import message_from_bytes, policy
from core.mime import build_mime


def _parse(raw):
    return message_from_bytes(base64.urlsafe_b64decode(raw), policy=policy.default)


def test_build_basic():
    raw, mid = build_mime("me@example.com", "dest@example.com", "Hello", "Body text")
    msg = _parse(raw)
    assert msg["From"] == "me@example.com"
    assert msg["To"] == "dest@example.com"
    assert msg["Subject"] == "Hello"
    assert msg["Message-ID"] == mid
    assert "Body text" in msg.get_content()


def test_build_reply_headers():
    raw, mid = build_mime("me@example.com", "dest@example.com", "Re: Subject", "ok",
                          in_reply_to="<orig@mail>")
    msg = _parse(raw)
    assert msg["In-Reply-To"] == "<orig@mail>"
    assert msg["References"] == "<orig@mail>"


def test_build_with_attachment():
    raw, mid = build_mime("me@example.com", "d@example.com", "S", "body",
                          attachments=[{"filename": "a.txt", "mime_type": "text/plain", "data": b"hello"}])
    msg = _parse(raw)
    assert msg.is_multipart()
    names = [p.get_filename() for p in msg.walk() if p.get_filename()]
    assert "a.txt" in names


def test_build_multipart_html():
    raw, mid = build_mime("me@example.com", "d@example.com", "S", "text", body_html="<b>html</b>", cc="c@example.com")
    msg = _parse(raw)
    assert msg["Cc"] == "c@example.com"
    assert msg.is_multipart()
    types = {p.get_content_type() for p in msg.walk()}
    assert "text/plain" in types and "text/html" in types
