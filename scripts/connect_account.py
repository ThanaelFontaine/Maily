#!/usr/bin/env python3
"""Connecte une boite Gmail en live via OAuth loopback, et range le token au Trousseau.

Usage:
  uv run python scripts/connect_account.py

Ouvre le navigateur pour le consentement Google. A l'ecran "app non verifiee" :
Parametres avances -> Continuer vers Maily. Le refresh token est ensuite stocke
dans le Trousseau, indexe par l'adresse email du compte connecte.
"""
from __future__ import annotations
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from core import auth, paths
from core.db import Database
from core.store import Store


def main():
    print("Ouverture du navigateur pour le consentement Google...")
    print("(Ecran 'app non verifiee' -> Parametres avances -> Continuer vers Maily)")
    email = auth.run_local_auth(open_browser=True)
    # Enregistrer le compte dans la base locale (le rail liste les comptes de la base).
    layout = paths.ensure_runtime_dirs(paths.runtime_dir())
    db = Database(layout["db"])
    Store(db).upsert_account(email)
    db.close()
    print(f"OK : boite connectee, token range et compte enregistre -> {email}")


if __name__ == "__main__":
    main()
