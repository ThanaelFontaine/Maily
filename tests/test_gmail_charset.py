import base64
from core.gmail import parse_gmail_message


def test_iso8859_1_body_not_corrupted():
    body = "Café déjà vu".encode("iso-8859-1")
    raw = {
        "id": "g1", "threadId": "t", "snippet": "", "internalDate": "1", "labelIds": ["INBOX"],
        "payload": {
            "mimeType": "text/html",
            "headers": [{"name": "Content-Type", "value": "text/html; charset=ISO-8859-1"},
                        {"name": "Subject", "value": "S"}],
            "body": {"data": base64.urlsafe_b64encode(body).decode()},
        },
    }
    fields, _ = parse_gmail_message(raw)
    assert "Café déjà vu" in fields["body_html"]
    assert "�" not in fields["body_html"]


def test_is_trashed_from_label():
    raw = {"id": "g", "threadId": "t", "internalDate": "1", "labelIds": ["TRASH"],
           "payload": {"mimeType": "text/plain", "headers": [], "body": {"data": ""}}}
    fields, _ = parse_gmail_message(raw)
    assert fields["is_trashed"] == 1
