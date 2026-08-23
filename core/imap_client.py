"""Client IMAP minimal (stdlib `imaplib`), pour Orange et autres fournisseurs
IMAP simples. Lecture INBOX + corbeille. Injectable : le syncer reçoit une
instance, ce qui permet de le tester avec un faux client sans réseau.

Volontairement léger : Orange est temporaire (cf. spec Phase 2).
"""
from __future__ import annotations
import imaplib
import datetime

# Dossiers Corbeille courants selon les serveurs (Orange = "Trash").
_TRASH_CANDIDATES = ["Trash", "INBOX.Trash", "Corbeille", "INBOX.Corbeille",
                     "Deleted Messages", "[Gmail]/Trash"]


class ImapError(Exception):
    pass


class ImapClient:
    def __init__(self, host, port, username, password):
        self.host = host
        self.port = int(port)
        self.username = username
        self.password = password
        self.conn = None

    def connect(self):
        try:
            self.conn = imaplib.IMAP4_SSL(self.host, self.port)
            self.conn.login(self.username, self.password)
        except (imaplib.IMAP4.error, OSError) as e:
            raise ImapError(f"connexion/identifiants IMAP invalides: {e}") from e
        return self

    def select_inbox(self) -> int:
        typ, _ = self.conn.select("INBOX", readonly=False)
        if typ != "OK":
            raise ImapError("selection INBOX impossible")
        typ, data = self.conn.status("INBOX", "(UIDVALIDITY)")
        # ex: b'INBOX (UIDVALIDITY 123456789)'
        try:
            return int(data[0].split(b"UIDVALIDITY")[1].strip(b" )").split()[0])
        except (IndexError, ValueError):
            return 0

    def search_uids(self, since: datetime.date | None = None, min_uid: int | None = None) -> list[int]:
        if min_uid is not None:
            crit = f"UID {min_uid}:*"
        elif since is not None:
            crit = f'SINCE {since.strftime("%d-%b-%Y")}'
        else:
            crit = "ALL"
        typ, data = self.conn.uid("SEARCH", None, crit)
        if typ != "OK" or not data or data[0] is None:
            return []
        uids = [int(x) for x in data[0].split()]
        # UID n:* renvoie parfois le dernier message même si <= min_uid : on filtre.
        if min_uid is not None:
            uids = [u for u in uids if u >= min_uid]
        return sorted(uids)

    def fetch(self, uid: int) -> tuple[bytes, bool]:
        """Renvoie (RFC822 brut, vu?) pour un UID."""
        typ, data = self.conn.uid("FETCH", str(uid), "(RFC822 FLAGS)")
        if typ != "OK" or not data or not isinstance(data[0], tuple):
            raise ImapError(f"fetch UID {uid} echoue")
        raw = data[0][1]
        flags = b" ".join(x for x in data if isinstance(x, (bytes, bytearray)))
        seen = b"\\Seen" in flags
        # les FLAGS peuvent aussi arriver dans l'entête du tuple data[0][0]
        if not seen and isinstance(data[0][0], (bytes, bytearray)):
            seen = b"\\Seen" in data[0][0]
        return raw, seen

    def move_to_trash(self, uid: int):
        trash = self._find_trash()
        if trash:
            # UID MOVE si dispo, sinon COPY + \Deleted + EXPUNGE.
            try:
                typ, _ = self.conn.uid("MOVE", str(uid), trash)
                if typ == "OK":
                    return
            except imaplib.IMAP4.error:
                pass
            self.conn.uid("COPY", str(uid), trash)
        self.conn.uid("STORE", str(uid), "+FLAGS", "(\\Deleted)")
        self.conn.expunge()

    def _find_trash(self):
        try:
            typ, boxes = self.conn.list()
        except imaplib.IMAP4.error:
            return _TRASH_CANDIDATES[0]
        names = b" ".join(b for b in (boxes or []) if isinstance(b, (bytes, bytearray)))
        for cand in _TRASH_CANDIDATES:
            if cand.encode() in names:
                return cand
        return _TRASH_CANDIDATES[0]

    def logout(self):
        try:
            if self.conn is not None:
                self.conn.logout()
        except imaplib.IMAP4.error:
            pass
        finally:
            self.conn = None
