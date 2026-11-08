import pytest
from core import db as dbmod


def test_connect_sets_pragmas(tmp_path):
    conn = dbmod.connect(tmp_path / "x.sqlite")
    assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert conn.execute("PRAGMA secure_delete").fetchone()[0] == 1
    conn.close()


@pytest.mark.skipif(not dbmod.fts_secure_delete_supported(), reason="SQLite older than 3.42")
def test_fts_secure_delete_option_is_set_once(tmp_path):
    d = dbmod.Database(tmp_path / "f.sqlite")
    assert d.fts_secure_delete is True
    row = d.read().execute("SELECT v FROM messages_fts_config WHERE k='secure-delete'").fetchone()
    assert str(row[0]) == "1"
    d.close()
    d2 = dbmod.Database(tmp_path / "f.sqlite")      # reopening keeps it
    assert d2.fts_secure_delete is True
    d2.close()


def test_checkpoint_truncate_empties_the_wal(tmp_path):
    d = dbmod.Database(tmp_path / "w.sqlite")
    with d.writer() as c:
        c.execute("INSERT INTO accounts(email) VALUES ('a@example.com')")
    assert d.checkpoint_truncate() is True
    wal = tmp_path / "w.sqlite-wal"
    assert (not wal.exists()) or wal.stat().st_size == 0
    d.close()


def test_apply_migrations_sets_user_version(tmp_path):
    conn = dbmod.connect(tmp_path / "m.sqlite")
    version = dbmod.apply_migrations(conn)
    assert version >= 1
    # idempotent: applying again changes nothing
    assert dbmod.apply_migrations(conn) == version
    conn.close()


def test_database_writer_serializes(database):
    with database.writer() as conn:
        conn.execute("INSERT INTO accounts(email) VALUES ('a@example.com')")
    rows = database.read().execute("SELECT email FROM accounts").fetchall()
    assert rows[0]["email"] == "a@example.com"
