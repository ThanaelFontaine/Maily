#!/usr/bin/env python3
"""Mode demonstration : l'interface de Maily sur des donnees fictives.

Sert a essayer l'interface, a developper le frontend et a produire les
captures d'ecran, SANS compte Google, sans reseau et sans jamais toucher le
vrai dossier de donnees ni les vrais secrets :

- la base est creee dans un dossier temporaire (ou celui passe en --data-dir,
  qui doit etre different du dossier standard de Maily) ;
- le jeton de l'API locale est genere en memoire, rien n'est ecrit dans
  secrets.enc ;
- l'envoi et la synchronisation sont desactives ; lu/non lu, archive et
  corbeille s'appliquent a la base de demonstration seulement.

Usage (depuis la racine du depot) :
  uv run python scripts/demo.py                    # dossier temporaire, port libre
  uv run python scripts/demo.py --port 8765 --data-dir /tmp/maily-demo

Puis ouvrir l'URL affichee dans un navigateur. Ctrl+C pour arreter.
"""
from __future__ import annotations
import argparse
import json
import os
import pathlib
import secrets
import sys
import tempfile
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from core import paths  # noqa: E402

_NOW_MS = int(time.time() * 1000)
_HOUR = 3600 * 1000
_DAY = 24 * _HOUR

ACCOUNTS = [
    {"email": "alex@example.com", "display_name": "Perso", "color": "#1a73e8", "provider": "gmail"},
    {"email": "alex.martin@example.org", "display_name": "Travail", "color": "#188038", "provider": "gmail"},
    {"email": "alex@example.net", "display_name": "Ancienne adresse", "color": "#e37400", "provider": "imap"},
]

LABELS = [
    {"id": "INBOX", "name": "INBOX", "type": "system"},
    {"id": "Label_1", "name": "Factures", "type": "user"},
    {"id": "Label_2", "name": "Voyages", "type": "user"},
]

_SIGNATURE = "<p style=\"color:#5e6368\">Camille<br>Équipe projet</p>"

MESSAGES = [
    # (compte, expediteur, sujet, apercu, html, age, labels, non lu, pièce jointe)
    (0, "Camille Durand <camille@example.com>", "Point d'avancement de jeudi",
     "Voici le compte rendu de la réunion et les prochaines étapes.",
     "<p>Bonjour Alex,</p><p>Voici le compte rendu de notre point de jeudi :</p>"
     "<ul><li>la maquette de la page d'accueil est validée ;</li>"
     "<li>la mise en ligne est prévue pour la fin du mois ;</li>"
     "<li>il reste à relire les textes de la FAQ.</li></ul>"
     "<p>Le document complet est en pièce jointe. Bonne journée !</p>" + _SIGNATURE,
     1 * _HOUR, ["INBOX", "UNREAD"], True, True),
    (0, "La Lettre du dimanche <lettre@news.example.com>", "Cinq idées de balades pour l'automne",
     "Forêts, côtes et villages : notre sélection de la semaine.",
     "<p><img src=\"https://news.example.com/banner.png\" alt=\"Bandeau\" width=\"600\"></p>"
     "<h2>Cinq idées de balades pour l'automne</h2>"
     "<p>Forêts, côtes et villages : notre sélection de la semaine, avec cartes et temps de marche.</p>"
     "<p><img src=\"https://news.example.com/pixel.gif\" width=\"1\" height=\"1\" alt=\"\"></p>",
     3 * _HOUR, ["INBOX", "UNREAD", "CATEGORY_PROMOTIONS"], True, False),
    (0, "Banque Exemple <no-reply@bank.example.com>", "Votre relevé de septembre est disponible",
     "Votre relevé de compte est disponible dans votre espace client.",
     "<p>Bonjour,</p><p>Votre relevé de compte de septembre est disponible dans votre espace client.</p>"
     "<p>Ceci est un message automatique, merci de ne pas y répondre.</p>",
     20 * _HOUR, ["INBOX", "CATEGORY_UPDATES", "Label_1"], False, False),
    (0, "Jordan Petit <jordan@example.org>", "Photos du week-end",
     "Je t'envoie le lien vers l'album, dis-moi si tu arrives à l'ouvrir.",
     "<p>Salut !</p><p>Je t'envoie le lien vers l'album du week-end. Dis-moi si tu arrives à l'ouvrir.</p><p>Jordan</p>",
     2 * _DAY, ["INBOX"], False, False),
    (0, "Train Exemple <billets@rail.example.com>", "Votre billet pour Lyon",
     "Départ 8 h 12, voiture 14, place 62.",
     "<p>Votre billet est confirmé.</p><table cellpadding=\"6\"><tr><td><b>Départ</b></td><td>8 h 12</td></tr>"
     "<tr><td><b>Voiture</b></td><td>14</td></tr><tr><td><b>Place</b></td><td>62</td></tr></table>",
     4 * _DAY, ["INBOX", "CATEGORY_UPDATES", "Label_2"], False, True),
    (0, "Réseau Social <notification@social.example.com>", "Vous avez 3 nouvelles notifications",
     "Sam et 2 autres personnes ont réagi à votre publication.",
     "<p>Sam et 2 autres personnes ont réagi à votre publication.</p>",
     5 * _DAY, ["INBOX", "CATEGORY_SOCIAL"], True, False),
    (1, "Morgan Leroy <morgan@example.org>", "Relecture du contrat",
     "J'ai ajouté mes remarques en commentaire, rien de bloquant.",
     "<p>Bonjour Alex,</p><p>J'ai ajouté mes remarques en commentaire dans le document, rien de bloquant.</p>"
     "<p>On en parle demain ?</p><p>Morgan</p>",
     5 * _HOUR, ["INBOX", "UNREAD"], True, False),
    (1, "Outil de tickets <support@tickets.example.org>", "[#4821] Problème de connexion résolu",
     "Le ticket a été fermé par l'équipe support.",
     "<p>Le ticket <b>#4821</b> a été fermé par l'équipe support.</p>",
     1 * _DAY, ["INBOX", "CATEGORY_UPDATES"], False, False),
    (2, "Association Exemple <contact@asso.example.net>", "Assemblée générale le 12 octobre",
     "Ordre du jour et formulaire de procuration.",
     "<p>Chers membres,</p><p>L'assemblée générale aura lieu le 12 octobre à 18 h. Ordre du jour ci-dessous.</p>",
     3 * _DAY, ["INBOX", "UNREAD"], True, False),
]


def seed(store) -> None:
    ids = [store.upsert_account(a["email"], display_name=a["display_name"], color=a["color"],
                                provider=a["provider"]) for a in ACCOUNTS]
    for aid in ids[:2]:
        store.replace_labels(aid, LABELS)
    for n, (acc, frm, subject, snippet, html, age, labels, unread, att) in enumerate(MESSAGES):
        aid = ids[acc]
        mid = store.upsert_message(
            aid, f"demo-{n}", thread_id=f"t-{n}", addr_from=frm, addr_to=ACCOUNTS[acc]["email"],
            subject=subject, snippet=snippet, body_html=html,
            body_text=snippet, internal_date=_NOW_MS - age, label_ids=json.dumps(labels),
            is_unread=1 if unread else 0, has_attachments=1 if att else 0)
        if att:
            store.replace_attachments(mid, [{"filename": "compte-rendu.pdf" if n == 0 else "billet.pdf",
                                             "mime_type": "application/pdf", "size": 48213,
                                             "gmail_attachment_id": f"att-{n}"}])


def _default_data_dir() -> pathlib.Path:
    saved = os.environ.pop(paths.DATA_DIR_ENV, None)
    try:
        return paths.runtime_dir().resolve()
    finally:
        if saved is not None:
            os.environ[paths.DATA_DIR_ENV] = saved


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="Interface de Maily sur des donnees fictives.")
    ap.add_argument("--data-dir", help="dossier de la base de demonstration (defaut : dossier temporaire)")
    ap.add_argument("--port", type=int, default=0, help="port local (defaut : un port libre)")
    args = ap.parse_args(argv)

    data_dir = pathlib.Path(args.data_dir).expanduser() if args.data_dir else \
        pathlib.Path(tempfile.mkdtemp(prefix="maily-demo-"))
    real = _default_data_dir()
    target = data_dir.resolve()
    if target == real or real in target.parents:
        raise SystemExit("Refus : --data-dir pointe vers le vrai dossier de Maily (ou un de ses "
                         "sous-dossiers). Choisis un autre dossier.")
    os.environ[paths.DATA_DIR_ENV] = str(data_dir)

    import uvicorn
    from api.app import create_app
    from app.bootstrap import _frontend_dir, free_port
    from core.db import Database
    from core.store import Store

    layout = paths.ensure_runtime_dirs(data_dir)
    store = Store(Database(layout["db"]))
    if not store.list_accounts():
        seed(store)

    def act_fn(message_id, action, add=None, remove=None):
        if action == "modify":
            store.apply_local_labels(message_id, add=add, remove=remove)
        elif action in ("trash", "untrash"):
            store.set_trashed(message_id, action == "trash")
        return {"ok": True}

    def send_fn(payload):
        raise RuntimeError("envoi desactive en mode demonstration")

    def download_fn(message_id, att_id):
        att = store.get_attachment(att_id)
        return b"%PDF-1.4\n% fichier de demonstration\n", "application/pdf", att["filename"]

    token = secrets.token_urlsafe(24)   # en memoire seulement, jamais ecrit sur le disque
    app = create_app(store, token, sync_fn=lambda account_id: 0, send_fn=send_fn, act_fn=act_fn,
                     download_fn=download_fn, frontend_dir=_frontend_dir())
    port = args.port or free_port()
    print(f"Maily (demonstration) : http://127.0.0.1:{port}/")
    print(f"Donnees fictives dans : {data_dir}")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
