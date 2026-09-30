#!/usr/bin/env python3
"""Enregistre dans la base locale les comptes deja connectes (jeton present dans le magasin chiffre).

Usage:
  uv run python scripts/register_accounts.py email1 [email2 ...]

Pour chaque email : verifie qu'un jeton existe dans secrets.enc, puis cree/actualise
la ligne compte en base (le rail de l'app liste les comptes de la base). N'ouvre
pas de navigateur. Idempotent.
"""
from __future__ import annotations
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from core import paths, secrets_store
from core.db import Database
from core.store import Store


def main():
    emails = sys.argv[1:]
    if not emails:
        sys.exit("Usage: register_accounts.py email1 [email2 ...]")
    layout = paths.ensure_runtime_dirs(paths.runtime_dir())
    db = Database(layout["db"])
    store = Store(db)
    for e in emails:
        if secrets_store.load_account_token(e):
            store.upsert_account(e)
            print(f"  enregistre : {e}")
        else:
            print(f"  IGNORE (aucun jeton enregistre, connecte-le d'abord) : {e}")
    db.close()
    print("Termine.")


if __name__ == "__main__":
    main()
