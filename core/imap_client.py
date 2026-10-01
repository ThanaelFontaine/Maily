"""Minimal IMAP client (stdlib `imaplib`), for Orange and other simple IMAP
providers. Reads folders, fetches messages, moves them to the trash.
Injectable: the syncer receives an instance, so it can be tested with a fake
client and no network.

Deliberately small: reading is the only goal (no SMTP).
"""
from __future__ import annotations
import imaplib
import re
import datetime

# Usual trash folder names across servers (Orange = "Trash"; "Corbeille" is
# the French name some servers use).
_TRASH_CANDIDATES = ["Trash", "INBOX.Trash", "Corbeille", "INBOX.Corbeille",
                     "Deleted Messages", "[Gmail]/Trash"]

# Separator of the IMAP message key: "{folder}\x1f{uidvalidity}\x1f{uid}".
# \x1f (unit separator) never appears in a folder name or a UID.
_KEY_SEP = "\x1f"


class ImapError(Exception):
    pass


def imap_msg_key(folder: str, uidvalidity, uid) -> str:
    return f"{folder}{_KEY_SEP}{uidvalidity}{_KEY_SEP}{uid}"


def parse_imap_key(key: str) -> tuple[str, int]:
    """(folder, uid) from an IMAP message key."""
    parts = str(key).split(_KEY_SEP)
    if len(parts) < 3:
        raise ValueError(f"invalid IMAP key: {key!r}")
    return parts[0], int(parts[-1])


def _quote(name: str) -> str:
    return '"' + name.replace('"', '\\"') + '"'


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
            raise ImapError(f"IMAP connection or credentials refused: {e}") from e
        return self

    def list_folders(self) -> list[str]:
        """Every selectable folder (INBOX first)."""
        try:
            typ, data = self.conn.list()
        except imaplib.IMAP4.error:
            return ["INBOX"]
        if typ != "OK" or not data:
            return ["INBOX"]
        names = []
        for line in data:
            if not isinstance(line, (bytes, bytearray)):
                continue
            s = line.decode(errors="replace")
            if "\\Noselect" in s:          # containers that cannot be selected
                continue
            quoted = re.findall(r'"((?:[^"\\]|\\.)*)"', s)
            name = quoted[-1].replace('\\"', '"') if quoted else s.split()[-1]
            if name:
                names.append(name)
        names = sorted(set(names), key=lambda n: (n != "INBOX", n.lower()))
        return names or ["INBOX"]

    def select_folder(self, name: str) -> int:
        typ, _ = self.conn.select(_quote(name), readonly=False)
        if typ != "OK":
            raise ImapError(f"cannot select {name!r}")
        typ, data = self.conn.status(_quote(name), "(UIDVALIDITY)")
        try:
            return int(data[0].split(b"UIDVALIDITY")[1].strip(b" )").split()[0])
        except (IndexError, ValueError, AttributeError):
            return 0

    def select_inbox(self) -> int:
        return self.select_folder("INBOX")

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
        # UID n:* sometimes returns the last message even if <= min_uid: filter it out.
        if min_uid is not None:
            uids = [u for u in uids if u >= min_uid]
        return sorted(uids)

    def fetch(self, uid: int) -> tuple[bytes, bool]:
        """Returns (raw RFC 822, seen?) for a UID."""
        typ, data = self.conn.uid("FETCH", str(uid), "(RFC822 FLAGS)")
        if typ != "OK" or not data or not isinstance(data[0], tuple):
            raise ImapError(f"fetching UID {uid} failed")
        raw = data[0][1]
        flags = b" ".join(x for x in data if isinstance(x, (bytes, bytearray)))
        seen = b"\\Seen" in flags
        # the FLAGS may also come in the header of the data[0][0] tuple
        if not seen and isinstance(data[0][0], (bytes, bytearray)):
            seen = b"\\Seen" in data[0][0]
        return raw, seen

    def move_to_trash(self, uid: int):
        trash = self._find_trash()
        if trash:
            # UID MOVE when available, otherwise COPY + \Deleted + EXPUNGE.
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
