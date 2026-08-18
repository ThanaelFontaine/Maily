from __future__ import annotations
import json
from core.db import Database

_MESSAGE_COLS = {
    "thread_id", "rfc822_message_id", "direction", "addr_from", "addr_to",
    "addr_cc", "addr_bcc", "subject", "snippet", "body_text", "body_html",
    "internal_date", "label_ids", "is_unread", "is_starred", "has_attachments",
    "is_trashed",
}


class Store:
    def __init__(self, database: Database):
        self.db = database

    def upsert_account(self, email, display_name=None, color=None) -> int:
        with self.db.writer() as c:
            c.execute(
                """INSERT INTO accounts(email, display_name, color) VALUES(?,?,?)
                   ON CONFLICT(email) DO UPDATE SET
                     display_name=COALESCE(excluded.display_name, accounts.display_name),
                     color=COALESCE(excluded.color, accounts.color)""",
                (email, display_name, color),
            )
            return c.execute("SELECT id FROM accounts WHERE email=?", (email,)).fetchone()[0]

    def list_accounts(self):
        return self.db.read().execute("SELECT * FROM accounts ORDER BY id").fetchall()

    def get_account(self, account_id):
        return self.db.read().execute("SELECT * FROM accounts WHERE id=?", (account_id,)).fetchone()

    def upsert_message(self, account_id, gmail_id, **fields) -> int:
        cols = {k: v for k, v in fields.items() if k in _MESSAGE_COLS}
        with self.db.writer() as c:
            row = c.execute(
                "SELECT id FROM messages WHERE account_id=? AND gmail_id=?",
                (account_id, gmail_id),
            ).fetchone()
            if row is None:
                keys = ["account_id", "gmail_id"] + list(cols.keys())
                vals = [account_id, gmail_id] + list(cols.values())
                ph = ",".join("?" * len(keys))
                c.execute(f"INSERT INTO messages({','.join(keys)}) VALUES({ph})", vals)
                return c.execute(
                    "SELECT id FROM messages WHERE account_id=? AND gmail_id=?",
                    (account_id, gmail_id),
                ).fetchone()[0]
            if cols:
                sets = ",".join(f"{k}=?" for k in cols) + ", updated_at=datetime('now')"
                c.execute(f"UPDATE messages SET {sets} WHERE id=?", list(cols.values()) + [row[0]])
            return row[0]

    def get_message(self, message_id):
        return self.db.read().execute("SELECT * FROM messages WHERE id=?", (message_id,)).fetchone()

    def search_messages(self, query, account_id=None, limit=50):
        sql = ("SELECT m.* FROM messages_fts f JOIN messages m ON m.id=f.rowid "
               "WHERE messages_fts MATCH ? AND m.is_trashed=0")
        params = [query]
        if account_id is not None:
            sql += " AND m.account_id=?"
            params.append(account_id)
        sql += " ORDER BY f.rank LIMIT ?"
        params.append(limit)
        return self.db.read().execute(sql, params).fetchall()

    def set_sync_state(self, account_id, key, value):
        with self.db.writer() as c:
            c.execute(
                """INSERT INTO sync_state(account_id, key, value) VALUES(?,?,?)
                   ON CONFLICT(account_id, key) DO UPDATE SET value=excluded.value""",
                (account_id, key, str(value)),
            )

    def get_sync_state(self, account_id, key):
        row = self.db.read().execute(
            "SELECT value FROM sync_state WHERE account_id=? AND key=?",
            (account_id, key),
        ).fetchone()
        return row[0] if row else None

    def list_messages(self, account_id=None, label=None, limit=50, offset=0):
        sql = "SELECT * FROM messages WHERE is_trashed=0"
        params = []
        if account_id is not None:
            sql += " AND account_id=?"
            params.append(account_id)
        if label:
            sql += " AND label_ids LIKE ?"
            params.append(f'%"{label}"%')
        sql += " ORDER BY internal_date DESC, id DESC LIMIT ? OFFSET ?"
        params += [limit, offset]
        return self.db.read().execute(sql, params).fetchall()

    def list_threads(self, account_id=None, limit=50, offset=0):
        sql = ("SELECT thread_id, account_id, MAX(internal_date) AS last_date, "
               "COUNT(*) AS message_count, "
               "(SELECT subject FROM messages m2 WHERE m2.thread_id=m.thread_id "
               " AND m2.is_trashed=0 ORDER BY internal_date DESC LIMIT 1) AS subject "
               "FROM messages m WHERE is_trashed=0")
        params = []
        if account_id is not None:
            sql += " AND account_id=?"
            params.append(account_id)
        sql += " GROUP BY thread_id ORDER BY last_date DESC LIMIT ? OFFSET ?"
        params += [limit, offset]
        return self.db.read().execute(sql, params).fetchall()

    def get_thread_messages(self, thread_id, account_id=None):
        sql = "SELECT * FROM messages WHERE thread_id=? AND is_trashed=0"
        params = [thread_id]
        if account_id is not None:
            sql += " AND account_id=?"
            params.append(account_id)
        sql += " ORDER BY internal_date ASC, id ASC"
        return self.db.read().execute(sql, params).fetchall()

    def add_outbox(self, account_id, addr_to, subject, body_text, body_html,
                   idempotency_key, addr_cc=None, in_reply_to=None, thread_id=None) -> int:
        with self.db.writer() as c:
            c.execute(
                """INSERT INTO outbox(account_id, addr_to, addr_cc, subject, body_text,
                     body_html, in_reply_to, thread_id, idempotency_key, status)
                   VALUES(?,?,?,?,?,?,?,?,?,'queued')""",
                (account_id, addr_to, addr_cc, subject, body_text, body_html,
                 in_reply_to, thread_id, idempotency_key),
            )
            return c.execute("SELECT id FROM outbox WHERE idempotency_key=?",
                             (idempotency_key,)).fetchone()[0]

    def mark_outbox(self, outbox_id, status, gmail_id=None, error=None):
        with self.db.writer() as c:
            c.execute(
                """UPDATE outbox SET status=?, gmail_id=COALESCE(?, gmail_id),
                     error=?, attempts=attempts+1,
                     sent_at=CASE WHEN ?='sent' THEN datetime('now') ELSE sent_at END
                   WHERE id=?""",
                (status, gmail_id, error, status, outbox_id),
            )

    def get_outbox(self, outbox_id):
        return self.db.read().execute("SELECT * FROM outbox WHERE id=?", (outbox_id,)).fetchone()

    def apply_local_labels(self, message_id, add=None, remove=None):
        add = set(add or [])
        remove = set(remove or [])
        with self.db.writer() as c:
            row = c.execute("SELECT label_ids FROM messages WHERE id=?", (message_id,)).fetchone()
            if not row:
                return
            labels = set(json.loads(row["label_ids"] or "[]"))
            labels = (labels | add) - remove
            c.execute(
                """UPDATE messages SET label_ids=?, is_unread=?, is_starred=?,
                     updated_at=datetime('now') WHERE id=?""",
                (json.dumps(sorted(labels)),
                 1 if "UNREAD" in labels else 0,
                 1 if "STARRED" in labels else 0,
                 message_id),
            )

    def set_trashed(self, message_id, trashed):
        with self.db.writer() as c:
            c.execute("UPDATE messages SET is_trashed=?, updated_at=datetime('now') WHERE id=?",
                      (1 if trashed else 0, message_id))
