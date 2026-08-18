from __future__ import annotations
import re
import sys
import sqlite3
import threading
import pathlib
from contextlib import contextmanager

_MIGRATION_RE = re.compile(r"^(\d{4})_.*\.sql$")


def migrations_dir() -> pathlib.Path:
    # En binaire figé (PyInstaller), les migrations sont embarquees a la racine.
    if getattr(sys, "frozen", False):
        return pathlib.Path(getattr(sys, "_MEIPASS", ".")) / "migrations"
    return pathlib.Path(__file__).resolve().parent.parent / "migrations"


def connect(db_path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


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

    def read(self) -> sqlite3.Connection:
        return connect(self.db_path)

    def close(self):
        self._write_conn.close()
