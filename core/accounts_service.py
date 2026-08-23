from __future__ import annotations
import base64
import os
import re
import threading
from googleapiclient.discovery import build
from core import auth
from core.auth import load_credentials
from core.gmail import GmailClient
from core.sync import Syncer
from core import sender
from core import secrets_store
from core.imap_client import ImapClient, ImapError, parse_imap_key
from core.imap_sync import ImapSyncer
from core.rfc822_parse import extract_part


class AddAccountInProgress(Exception):
    """Un ajout de compte est deja en cours (le flow OAuth loopback est mono-instance)."""
    pass


# Un seul ajout a la fois : le serveur loopback OAuth se lie a un port libre et
# deux flows concurrents peuvent se marcher dessus / ouvrir deux navigateurs.
_add_account_lock = threading.Lock()


def add_google_account(store, timeout_seconds: int | None = 180) -> dict:
    """Lance le consentement Google (navigateur systeme), enregistre le compte.

    Retourne {"account_id": int, "email": str}. Leve ReauthRequired si le client
    OAuth n'est pas configure, AuthTimeout en cas d'abandon, AddAccountInProgress
    si un ajout est deja en cours.
    """
    if not _add_account_lock.acquire(blocking=False):
        raise AddAccountInProgress("Un ajout de compte est deja en cours.")
    try:
        email = auth.run_local_auth(open_browser=True, timeout_seconds=timeout_seconds)
        account_id = store.upsert_account(email)
        return {"account_id": account_id, "email": email}
    finally:
        _add_account_lock.release()


def _provider(store, account_id) -> str:
    acc = store.get_account(account_id)
    return (dict(acc).get("provider") or "gmail") if acc else "gmail"


def build_imap_client(email) -> ImapClient:
    creds = secrets_store.load_imap_credentials(email)
    if not creds:
        raise ValueError(f"aucun identifiant IMAP pour {email}")
    return ImapClient(creds["host"], creds["port"], creds["username"], creds["password"])


def _imap_fetch_raw(email, gmail_id) -> bytes:
    folder, uid = parse_imap_key(gmail_id)
    c = build_imap_client(email)
    c.connect()
    c.select_folder(folder)
    try:
        raw, _seen = c.fetch(uid)
    finally:
        c.logout()
    return raw


def add_imap_account(store, email, password, host="imap.orange.fr", port=993) -> dict:
    """Connecte un compte IMAP (Orange...) : teste le login, stocke les creds
    chiffrés, crée le compte `provider='imap'`. Lève ImapError si login/connexion
    échoue, AddAccountInProgress si un ajout est déjà en cours."""
    if not _add_account_lock.acquire(blocking=False):
        raise AddAccountInProgress("Un ajout de compte est deja en cours.")
    try:
        creds = {"host": host, "port": int(port), "username": email, "password": password}
        client = ImapClient(**creds)
        client.connect()          # lève ImapError si identifiants/connexion KO
        client.select_inbox()
        client.logout()
        secrets_store.save_imap_credentials(email, creds)
        account_id = store.upsert_account(email, provider="imap")
        return {"account_id": account_id, "email": email}
    finally:
        _add_account_lock.release()


def logout_account(store, account_id) -> None:
    """Deconnecte un compte : supprime ses identifiants chiffres (token Google ou
    creds IMAP selon le provider) ET son cache local (messages, PJ, labels...).
    Reversible : reconnecter le compte relance un backfill. No-op si inconnu."""
    acc = store.get_account(account_id)
    if acc is not None:
        acc = dict(acc)
        provider = acc.get("provider") or "gmail"
        email = acc.get("email")
        if provider == "imap":
            secrets_store.delete_imap_credentials(email)
        else:
            secrets_store.delete_account_token(email)
    store.delete_account(account_id)


def _safe_name(name: str) -> str:
    name = re.sub(r"[^A-Za-z0-9._-]", "_", name or "file")
    return name[:120] or "file"


def _b64url_to_bytes(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def export_eml(store, message_id) -> tuple[bytes, str]:
    """Renvoie (octets RFC822 bruts, nom de fichier .eml) pour un message.
    Branche selon le provider : Gmail (format raw) ou IMAP (fetch raw)."""
    m = store.get_message(message_id)
    if not m:
        raise ValueError("message introuvable")
    m = dict(m)
    acc = store.get_account(m["account_id"])
    acc = dict(acc) if acc else {}
    provider = acc.get("provider") or "gmail"
    if provider == "imap":
        raw = _imap_fetch_raw(acc["email"], m["gmail_id"])
    else:
        resp = build_gmail_client(acc["email"]).get_message(m["gmail_id"], fmt="raw")
        raw = _b64url_to_bytes(resp["raw"])
    subject = (m.get("subject") or "").strip()
    filename = (_safe_name(subject) + ".eml") if subject else f"message-{message_id}.eml"
    return raw, filename


def fetch_attachment(store, email, message_id, att_id, attachments_dir):
    att = store.get_attachment(att_id)
    if not att or att["owner_id"] != message_id or att["owner_kind"] != "message":
        raise ValueError("piece jointe introuvable")
    lp = att["local_path"]
    if lp and os.path.exists(lp):
        with open(lp, "rb") as f:
            return f.read(), att["mime_type"], att["filename"]
    m = store.get_message(message_id)
    if _provider(store, m["account_id"]) == "imap":
        raw = _imap_fetch_raw(email, m["gmail_id"])
        data, _mime, _fn = extract_part(raw, att["gmail_attachment_id"])
    else:
        client = build_gmail_client(email)
        resp = client.get_attachment(m["gmail_id"], att["gmail_attachment_id"])
        data = base64.urlsafe_b64decode(resp["data"])
    os.makedirs(attachments_dir, exist_ok=True)
    path = os.path.join(attachments_dir, f"{att_id}_{_safe_name(att['filename'])}")
    with open(path, "wb") as f:
        f.write(data)
    store.set_attachment_path(att_id, path)
    return data, att["mime_type"], att["filename"]


def build_gmail_client(email) -> GmailClient:
    creds = load_credentials(email)
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)
    return GmailClient(service)


def refresh_labels(store, email, account_id) -> int:
    if _provider(store, account_id) == "imap":
        return 0                      # pas de libellés IMAP (INBOX synthétique)
    client = build_gmail_client(email)
    labels = client.list_labels()
    store.replace_labels(account_id, labels)
    return len(labels)


def modify_message(store, email, message_id, add=None, remove=None) -> dict:
    m = store.get_message(message_id)
    if not m:
        raise ValueError("message introuvable")
    # IMAP : pas d'API de libellés -> on applique en local (marquer lu, archiver).
    if _provider(store, m["account_id"]) != "imap":
        build_gmail_client(email).modify(m["gmail_id"], add=add, remove=remove)
    store.apply_local_labels(message_id, add=add, remove=remove)
    return {"ok": True}


def trash_message(store, email, message_id) -> dict:
    m = store.get_message(message_id)
    if not m:
        raise ValueError("message introuvable")
    if _provider(store, m["account_id"]) == "imap":
        folder, uid = parse_imap_key(m["gmail_id"])
        c = build_imap_client(email)
        c.connect()
        c.select_folder(folder)
        try:
            c.move_to_trash(uid)
        finally:
            c.logout()
    else:
        build_gmail_client(email).trash(m["gmail_id"])
    store.set_trashed(message_id, True)
    return {"ok": True}


def untrash_message(store, email, message_id) -> dict:
    m = store.get_message(message_id)
    if not m:
        raise ValueError("message introuvable")
    if _provider(store, m["account_id"]) == "imap":
        raise ValueError("Restauration non disponible pour un compte Orange (IMAP).")
    build_gmail_client(email).untrash(m["gmail_id"])
    store.set_trashed(message_id, False)
    return {"ok": True}


_MAX_SEND_BYTES = 25 * 1024 * 1024


def send_from_account(store, email, account_id, payload) -> dict:
    attachments = []
    total = 0
    for a in payload.get("attachments") or []:
        data = base64.b64decode(a["data"])
        total += len(data)
        attachments.append({"filename": a.get("filename"), "mime_type": a.get("mime_type"), "data": data})
    if total > _MAX_SEND_BYTES:
        raise ValueError("Pieces jointes trop volumineuses (max 25 Mo au total pour l'envoi simple).")
    client = build_gmail_client(email)
    return sender.send_message(
        store, client, account_id, email,
        payload["to"], payload.get("subject", ""), payload.get("body_text", ""),
        body_html=payload.get("body_html"), cc=payload.get("cc"),
        in_reply_to=payload.get("in_reply_to"), thread_id=payload.get("thread_id"),
        attachments=attachments, idempotency_key=payload.get("idempotency_key"),
    )


def sync_account(store, email, account_id, full=False, query=None) -> int:
    if _provider(store, account_id) == "imap":
        from core.config import load_settings
        months = load_settings().backfill_months
        syncer = ImapSyncer(store, build_imap_client(email), account_id, backfill_months=months)
        return syncer.backfill() if full else syncer.incremental()
    client = build_gmail_client(email)
    try:
        store.replace_labels(account_id, client.list_labels())
    except Exception:
        pass
    syncer = Syncer(store, client, account_id)
    if full:
        return syncer.backfill(query=query)
    return syncer.incremental()
