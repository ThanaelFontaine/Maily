from __future__ import annotations
import base64
import json
import re
import time
from googleapiclient.errors import HttpError

_RETRYABLE = {429, 500, 502, 503}


# --------------------------------------------------------------------------- #
# Parsing (fonction pure, sans reseau)
# --------------------------------------------------------------------------- #

def _b64url_decode(data: str, charset: str = "utf-8") -> str:
    if not data:
        return ""
    padding = "=" * (-len(data) % 4)
    raw = base64.urlsafe_b64decode(data + padding)
    try:
        return raw.decode(charset or "utf-8", errors="replace")
    except (LookupError, TypeError):
        return raw.decode("utf-8", errors="replace")


def _headers_map(part: dict) -> dict:
    return {h["name"].lower(): h["value"] for h in part.get("headers", [])}


def _charset_of(part: dict) -> str:
    ct = _headers_map(part).get("content-type", "")
    m = re.search(r'charset=["\']?([\w\-]+)', ct, re.I)
    return m.group(1) if m else "utf-8"


def _walk(part, bodies, attachments):
    mime = part.get("mimeType", "")
    filename = part.get("filename") or ""
    body = part.get("body", {}) or {}
    if filename and body.get("attachmentId"):
        hdrs = _headers_map(part)
        cid = hdrs.get("content-id", "").strip("<>") or None
        attachments.append({
            "filename": filename,
            "mime_type": mime,
            "size": body.get("size"),
            "gmail_attachment_id": body["attachmentId"],
            "content_id": cid,
        })
    elif mime == "text/plain" and body.get("data"):
        bodies.setdefault("text", _b64url_decode(body["data"], _charset_of(part)))
    elif mime == "text/html" and body.get("data"):
        bodies.setdefault("html", _b64url_decode(body["data"], _charset_of(part)))
    for sub in part.get("parts", []) or []:
        _walk(sub, bodies, attachments)


def parse_gmail_message(raw: dict) -> tuple[dict, list[dict]]:
    payload = raw.get("payload", {}) or {}
    headers = _headers_map(payload)
    bodies: dict = {}
    attachments: list = []
    _walk(payload, bodies, attachments)
    labels = raw.get("labelIds", []) or []
    fields = {
        "thread_id": raw.get("threadId"),
        "rfc822_message_id": headers.get("message-id"),
        "direction": "out" if "SENT" in labels else "in",
        "addr_from": headers.get("from"),
        "addr_to": headers.get("to"),
        "addr_cc": headers.get("cc"),
        "addr_bcc": headers.get("bcc"),
        "subject": headers.get("subject"),
        "snippet": raw.get("snippet"),
        "body_text": bodies.get("text"),
        "body_html": bodies.get("html"),
        "internal_date": int(raw["internalDate"]) if raw.get("internalDate") else None,
        "label_ids": json.dumps(labels),
        "is_unread": 1 if "UNREAD" in labels else 0,
        "is_starred": 1 if "STARRED" in labels else 0,
        "is_trashed": 1 if "TRASH" in labels else 0,
        "has_attachments": 1 if attachments else 0,
    }
    return fields, attachments


# --------------------------------------------------------------------------- #
# Client Gmail (appels reseau isoles, injectable pour les tests)
# --------------------------------------------------------------------------- #

class HistoryExpired(Exception):
    pass


class GmailClient:
    def __init__(self, service):
        self.service = service

    def _execute(self, request, _sleep=time.sleep, max_attempts=5):
        delay = 1.0
        for attempt in range(max_attempts):
            try:
                return request.execute()
            except HttpError as e:
                status = getattr(e, "status_code", None) or getattr(getattr(e, "resp", None), "status", None)
                if status in _RETRYABLE and attempt < max_attempts - 1:
                    _sleep(delay)
                    delay = min(delay * 2, 30.0)
                    continue
                raise

    def list_message_ids(self, query=None, page_token=None, max_results=100):
        req = self.service.users().messages().list(
            userId="me", q=query, pageToken=page_token, maxResults=max_results)
        resp = self._execute(req)
        ids = [m["id"] for m in resp.get("messages", [])]
        return ids, resp.get("nextPageToken")

    def get_message(self, gmail_id, fmt="full"):
        req = self.service.users().messages().get(userId="me", id=gmail_id, format=fmt)
        return self._execute(req)

    def list_history(self, start_history_id, page_token=None):
        req = self.service.users().history().list(
            userId="me", startHistoryId=start_history_id, pageToken=page_token)
        try:
            resp = self._execute(req)
        except HttpError as e:
            status = getattr(e, "status_code", None) or getattr(getattr(e, "resp", None), "status", None)
            if status == 404:
                raise HistoryExpired(str(e)) from e
            raise
        return resp.get("history", []), resp.get("nextPageToken"), resp.get("historyId")

    def get_profile(self):
        return self._execute(self.service.users().getProfile(userId="me"))

    def list_labels(self):
        resp = self._execute(self.service.users().labels().list(userId="me"))
        return resp.get("labels", [])

    def send(self, raw, thread_id=None):
        body = {"raw": raw}
        if thread_id:
            body["threadId"] = thread_id
        return self._execute(self.service.users().messages().send(userId="me", body=body))

    def modify(self, gmail_id, add=None, remove=None):
        body = {}
        if add:
            body["addLabelIds"] = list(add)
        if remove:
            body["removeLabelIds"] = list(remove)
        return self._execute(self.service.users().messages().modify(userId="me", id=gmail_id, body=body))

    def trash(self, gmail_id):
        return self._execute(self.service.users().messages().trash(userId="me", id=gmail_id))

    def untrash(self, gmail_id):
        return self._execute(self.service.users().messages().untrash(userId="me", id=gmail_id))

    def get_attachment(self, gmail_id, attachment_id):
        return self._execute(self.service.users().messages().attachments().get(
            userId="me", messageId=gmail_id, id=attachment_id))
