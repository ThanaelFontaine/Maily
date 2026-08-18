#!/usr/bin/env python3
"""Stocke le client OAuth (client_id/secret) dans le Trousseau, sans jamais exposer le secret.

Usage:
  uv run python scripts/store_client_config.py /chemin/vers/client_secret_xxx.json
  uv run python scripts/store_client_config.py        # mode interactif (saisie masquee)

Le client_secret n'est ni affiche ni logge. Il est ecrit uniquement dans le
Trousseau macOS (service "Maily"). macOS peut afficher une demande d'acces au
Trousseau : cliquer "Autoriser".
"""
from __future__ import annotations
import json
import sys
import getpass
from core import secrets_store


def from_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    node = data.get("installed") or data.get("web") or data
    cid = node.get("client_id")
    secret = node.get("client_secret")
    if not cid or not secret:
        sys.exit("JSON invalide : client_id/client_secret introuvables "
                 "(attendu un identifiant OAuth de type 'Application de bureau').")
    return cid, secret


def interactive():
    cid = input("Client ID: ").strip()
    secret = getpass.getpass("Client secret (saisie masquee, rien ne s'affiche): ").strip()
    if not cid or not secret:
        sys.exit("client_id/client_secret vides.")
    return cid, secret


def main():
    if len(sys.argv) > 1:
        cid, secret = from_json(sys.argv[1])
    else:
        cid, secret = interactive()
    secrets_store.save_client_config(cid, secret)
    tail = cid[-16:] if len(cid) > 16 else cid
    print(f"OK : identifiants client stockes dans le Trousseau (client_id ...{tail}).")
    print("Le client_secret n'a jamais ete affiche.")


if __name__ == "__main__":
    main()
