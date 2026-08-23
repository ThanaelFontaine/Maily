from email.message import EmailMessage
from core.rfc822_parse import parse_rfc822, extract_part


def _sample() -> bytes:
    m = EmailMessage()
    m["From"] = "Alice <alice@orange.fr>"
    m["To"] = "bob@exemple.fr"
    m["Cc"] = "carol@exemple.fr"
    m["Subject"] = "Réunion café ☕"
    m["Message-ID"] = "<abc123@orange.fr>"
    m["Date"] = "Mon, 18 Aug 2025 10:30:00 +0200"
    m.set_content("Bonjour, ceci est le corps texte.")
    m.add_alternative("<p>Bonjour, <b>HTML</b>.</p>", subtype="html")
    m.add_attachment(b"%PDF-1.4 fake", maintype="application", subtype="pdf",
                     filename="facture.pdf")
    return m.as_bytes()


def test_parse_headers_and_bodies():
    fields, atts = parse_rfc822(_sample())
    assert fields["addr_from"] == "Alice <alice@orange.fr>"
    assert fields["addr_to"] == "bob@exemple.fr"
    assert fields["addr_cc"] == "carol@exemple.fr"
    assert fields["subject"] == "Réunion café ☕"
    assert fields["rfc822_message_id"] == "<abc123@orange.fr>"
    assert fields["thread_id"] == "<abc123@orange.fr>"      # fil = message-id
    assert "corps texte" in fields["body_text"]
    assert "<b>HTML</b>" in fields["body_html"]
    assert fields["direction"] == "in"
    assert fields["has_attachments"] == 1
    # date -> epoch ms (2025-08-18 08:30 UTC)
    assert fields["internal_date"] == 1755505800000


def test_parse_attachments_metadata():
    _fields, atts = parse_rfc822(_sample())
    assert len(atts) == 1
    a = atts[0]
    assert a["filename"] == "facture.pdf"
    assert a["mime_type"] == "application/pdf"
    assert a["size"] == len(b"%PDF-1.4 fake")
    assert a["gmail_attachment_id"] == "imap:0"


def test_extract_part_returns_bytes():
    raw = _sample()
    data, mime, filename = extract_part(raw, "imap:0")
    assert data == b"%PDF-1.4 fake"
    assert mime == "application/pdf"
    assert filename == "facture.pdf"


def test_parse_plain_only():
    m = EmailMessage()
    m["From"] = "x@y.co"
    m["Subject"] = "Simple"
    m["Date"] = "Mon, 18 Aug 2025 10:30:00 +0200"
    m.set_content("juste du texte")
    fields, atts = parse_rfc822(m.as_bytes())
    assert fields["body_text"].strip() == "juste du texte"
    assert fields["has_attachments"] == 0
    assert atts == []
