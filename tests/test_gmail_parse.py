import base64, json
from core.gmail import parse_gmail_message


def _b64(s):
    return base64.urlsafe_b64encode(s.encode()).decode()


def test_parse_simple_multipart():
    raw = {
        "id": "g1", "threadId": "t1", "snippet": "apercu",
        "internalDate": "1700000000000",
        "labelIds": ["INBOX", "UNREAD"],
        "payload": {
            "mimeType": "multipart/alternative",
            "headers": [
                {"name": "From", "value": "Rec <rh@example.org>"},
                {"name": "To", "value": "me@example.com"},
                {"name": "Subject", "value": "Candidature"},
                {"name": "Message-ID", "value": "<abc@mail>"},
            ],
            "parts": [
                {"mimeType": "text/plain", "body": {"data": _b64("hello recruiter")}},
                {"mimeType": "text/html", "body": {"data": _b64("<p>hello</p>")}},
            ],
        },
    }
    fields, atts = parse_gmail_message(raw)
    assert fields["subject"] == "Candidature"
    assert fields["addr_from"] == "Rec <rh@example.org>"
    assert fields["body_text"] == "hello recruiter"
    assert fields["body_html"] == "<p>hello</p>"
    assert fields["direction"] == "in"
    assert fields["is_unread"] == 1
    assert fields["is_starred"] == 0
    assert fields["has_attachments"] == 0
    assert fields["internal_date"] == 1700000000000
    assert fields["rfc822_message_id"] == "<abc@mail>"
    assert json.loads(fields["label_ids"]) == ["INBOX", "UNREAD"]
    assert atts == []


def test_parse_detects_attachment_and_sent():
    raw = {
        "id": "g2", "threadId": "t2", "snippet": "x", "internalDate": "1700000000001",
        "labelIds": ["SENT"],
        "payload": {
            "mimeType": "multipart/mixed",
            "headers": [{"name": "Subject", "value": "Sent"}],
            "parts": [
                {"mimeType": "text/plain", "body": {"data": _b64("body")}},
                {"mimeType": "application/pdf", "filename": "cv.pdf",
                 "headers": [{"name": "Content-ID", "value": "<cid123>"}],
                 "body": {"attachmentId": "att1", "size": 12345}},
            ],
        },
    }
    fields, atts = parse_gmail_message(raw)
    assert fields["direction"] == "out"
    assert fields["has_attachments"] == 1
    assert len(atts) == 1
    assert atts[0]["filename"] == "cv.pdf"
    assert atts[0]["gmail_attachment_id"] == "att1"
    assert atts[0]["mime_type"] == "application/pdf"
    assert atts[0]["content_id"] == "cid123"
