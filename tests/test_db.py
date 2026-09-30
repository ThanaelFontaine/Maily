from core import db as dbmod


def test_connect_sets_pragmas(tmp_path):
    conn = dbmod.connect(tmp_path / "x.sqlite")
    assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    conn.close()


def test_apply_migrations_sets_user_version(tmp_path):
    conn = dbmod.connect(tmp_path / "m.sqlite")
    version = dbmod.apply_migrations(conn)
    assert version >= 1
    # idempotent : re-appliquer ne change rien
    assert dbmod.apply_migrations(conn) == version
    conn.close()


def test_database_writer_serializes(database):
    with database.writer() as conn:
        conn.execute("INSERT INTO accounts(email) VALUES ('a@example.com')")
    rows = database.read().execute("SELECT email FROM accounts").fetchall()
    assert rows[0]["email"] == "a@example.com"
