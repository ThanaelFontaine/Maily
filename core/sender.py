from __future__ import annotations
from core.mime import build_mime


def send_message(store, client, account_id, sender_addr, to, subject, body_text,
                 body_html=None, cc=None, in_reply_to=None, references=None,
                 thread_id=None, attachments=None):
    raw, mid = build_mime(sender_addr, to, subject, body_text, body_html=body_html,
                          cc=cc, in_reply_to=in_reply_to, references=references,
                          attachments=attachments)
    oid = store.add_outbox(account_id, to, subject, body_text, body_html, mid,
                           addr_cc=cc, in_reply_to=in_reply_to, thread_id=thread_id)
    store.mark_outbox(oid, "sending")
    try:
        resp = client.send(raw, thread_id=thread_id)
    except Exception as e:
        store.mark_outbox(oid, "failed", error=str(e))
        raise
    store.mark_outbox(oid, "sent", gmail_id=resp.get("id"))
    return {"outbox_id": oid, "gmail_id": resp.get("id"), "message_id": mid}
