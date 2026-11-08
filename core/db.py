from __future__ import annotations
import re
import sys
import sqlite3
import threading
import pathlib
from contextlib import contextmanager

_MIGRATION_RE = re.compile(r"^(\d{4})_.*\.sql$")


def migrations_dir() -> pathlib.Path:
    # In a frozen binary (PyInstaller), the migrations are embedded at the root.
    if getattr(sys, "frozen", False):
        return pathlib.Path(getattr(sys, "_MEIPASS", ".")) / "migrations"
    return pathlib.Path(__file__).resolve().parent.parent / "migrations"


def connect(db_path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    # Deleted content is overwritten with zeros in the file instead of being
    # left in free pages (account disconnection must really erase the mail).
    conn.execute("PRAGMA secure_delete=ON")
    return conn


FTS_SECURE_DELETE_MIN_SQLITE = (3, 42, 0)


def fts_secure_delete_supported() -> bool:
    """True when the embedded SQLite has the FTS5 `secure-delete` option (3.42+)."""
    return sqlite3.sqlite_version_info >= FTS_SECURE_DELETE_MIN_SQLITE


def ensure_fts_secure_delete(conn: sqlite3.Connection) -> bool:
    """Sets, once, the FTS5 `secure-delete` option of `messages_fts`, so that a
    deleted message also disappears from the search index. Returns whether the
    option is active (False on an SQLite older than 3.42: the caller then
    rebuilds the index after a deletion)."""
    if not fts_secure_delete_supported():
        return False
    try:
        row = conn.execute("SELECT v FROM messages_fts_config WHERE k='secure-delete'").fetchone()
        if row is not None and str(row[0]) == "1":
            return True
        conn.execute("INSERT INTO messages_fts(messages_fts, rank) VALUES('secure-delete', 1)")
        conn.commit()
        return True
    except sqlite3.Error:
        return False


def apply_migrations(conn: sqlite3.Connection, migrations_path=None) -> int:
    path = pathlib.Path(migrations_path) if migrations_path else migrations_dir()
    current = conn.execute("PRAGMA user_version").fetchone()[0]
    files = []
    for p in sorted(path.glob("*.sql")):
        m = _MIGRATION_RE.match(p.name)
        if m:
            files.append((int(m.group(1)), p))
    files.sort()
    applied = current
    for num, p in files:
        if num <= current:
            continue
        sql = p.read_text(encoding="utf-8")
        try:
            conn.executescript("BEGIN;\n" + sql + f"\nPRAGMA user_version={num};\nCOMMIT;")
        except sqlite3.Error:
            conn.execute("ROLLBACK")
            raise
        applied = num
    return applied


class Database:
    def __init__(self, db_path):
        self.db_path = str(db_path)
        self._write_conn = connect(self.db_path)
        apply_migrations(self._write_conn)
        self.fts_secure_delete = ensure_fts_secure_delete(self._write_conn)
        self._lock = threading.Lock()

    @contextmanager
    def writer(self):
        with self._lock:
            try:
                yield self._write_conn
                self._write_conn.commit()
            except Exception:
                self._write_conn.rollback()
                raise

    def rebuild_fts(self) -> None:
        """Rewrites the whole full-text index from the `messages` table (drops
        the old index pages, which `secure_delete` then zeroes)."""
        with self.writer() as c:
            c.execute("INSERT INTO messages_fts(messages_fts) VALUES('rebuild')")

    def checkpoint_truncate(self) -> bool:
        """Folds the write-ahead log into the database file and empties it, so
        that no older copy of a deleted page stays in `-wal`. Never waits for
        another connection: returns False when it could not finish."""
        with self._lock:
            conn = self._write_conn
            conn.execute("PRAGMA busy_timeout=0")
            try:
                row = conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
                return row is not None and row[0] == 0
            except sqlite3.Error:
                return False
            finally:
                conn.execute("PRAGMA busy_timeout=5000")

    def read(self) -> sqlite3.Connection:
        return connect(self.db_path)

    def close(self):
        self._write_conn.close()
