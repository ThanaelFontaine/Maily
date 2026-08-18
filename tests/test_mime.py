import base64
from email import message_from_bytes, policy
from core.mime import build_mime


def _parse(raw):
    return message_from_bytes(base64.urlsafe_b64decode(raw), policy=policy.default)


def test_build_basic():
    raw, mid = build_mime("me@example.org", "dest@x.co", "Bonjour", "Corps texte")
    msg = _parse(raw)
    assert msg["From"] == "me@example.org"
    assert msg["To"] == "dest@x.co"
    assert msg["Subject"] == "Bonjour"
    assert msg["Message-ID"] == mid
    assert "Corps texte" in msg.get_content()


def test_build_reply_headers():
    raw, mid = build_mime("me@example.org", "dest@x.co", "Re: Sujet", "ok",
                          in_reply_to="<orig@mail>")
    msg = _parse(raw)
    assert msg["In-Reply-To"] == "<orig@mail>"
    assert msg["References"] == "<orig@mail>"


def test_build_multipart_html():
    raw, mid = build_mime("me@example.org", "d@x.co", "S", "texte", body_html="<b>html</b>", cc="c@x.co")
    msg = _parse(raw)
    assert msg["Cc"] == "c@x.co"
    assert msg.is_multipart()
    types = {p.get_content_type() for p in msg.walk()}
    assert "text/plain" in types and "text/html" in types
