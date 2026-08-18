from __future__ import annotations
import base64
from email.message import EmailMessage
from email.utils import make_msgid, formatdate


def build_mime(sender, to, subject, body_text, body_html=None, cc=None,
               in_reply_to=None, references=None, message_id=None):
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to
    if cc:
        msg["Cc"] = cc
    msg["Subject"] = subject or ""
    mid = message_id or make_msgid()
    msg["Message-ID"] = mid
    msg["Date"] = formatdate(localtime=True)
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = references or in_reply_to
    msg.set_content(body_text or "")
    if body_html:
        msg.add_alternative(body_html, subtype="html")
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    return raw, mid
