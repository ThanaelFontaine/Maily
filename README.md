# Maily

Outil email **local** multi-comptes (lecture + envoi) pour Gmail / Google Workspace, avec une vraie interface desktop, deux thèmes (Frutiger Aero et DedSec), et un accès de premier ordre pour des automatisations Claude. Tout reste **sur ta machine** : les mails sont synchronisés dans une base SQLite locale, les identifiants dans le Trousseau. Pas de serveur, pas de cloud tiers.

## Fonctionnalités

- **Multi-comptes Gmail** (Workspace et Gmail grand public mélangés), vue unifiée + par profil.
- **Lecture** : liste, rendu HTML nettoyé et sûr (anti pixel espion), images intégrées (`cid:`) affichées, pièces jointes téléchargeables.
- **Envoi / Réponse / Transfert** avec pièces jointes.
- **Organisation** : lu/non-lu (auto à l'ouverture), archiver, corbeille (réversible).
- **Recherche** locale plein texte.
- **Onglets de mails** : ⌘/Ctrl + clic ouvre un mail dans un onglet dédié.
- **Deux thèmes** : Frutiger Aero (verre, par défaut) et DedSec (sombre/glitch), bascule en un clic.
- **Réglage images** : bloquées par défaut (vie privée), activables globalement.
- **Accès Claude** : base SQLite (vues stables `v1_*`) + API HTTP locale + `runtime.json`.

## Prérequis

- macOS (Apple Silicon ou Intel), Windows ou Linux.
- [`uv`](https://docs.astral.sh/uv/) (gère Python et les dépendances).
- Un compte Google et **tes propres identifiants OAuth** (gratuits, voir ci-dessous). Aucun serveur ni compte payant requis.

## Installation

```bash
git clone git@github.com:ThanaelFontaine/fetch-multi-mail-viewer-sender.git
cd fetch-multi-mail-viewer-sender
uv python install 3.12
uv sync
```

## Configuration Google (une fois, gratuit)

L'app utilise **tes propres identifiants** (modèle « BYO credentials », comme rclone/GAM) : aucune vérification Google, données 100 % locales.

1. Suis le guide pas à pas : [`docs/guide-google-cloud-byo.md`](docs/guide-google-cloud-byo.md) (créer un projet Google Cloud, activer l'API Gmail, écran de consentement **External**, publier « In production », créer un identifiant OAuth **Application de bureau**).
2. Enregistre le `client_id`/`client_secret` dans le Trousseau (le secret ne s'affiche jamais) :
   ```bash
   uv run python scripts/store_client_config.py ~/Downloads/client_secret_*.json
   ```
3. Connecte chaque boîte (ouvre le navigateur pour le consentement) :
   ```bash
   uv run python scripts/connect_account.py
   ```
   À l'écran « application non vérifiée » : *Paramètres avancés → Continuer* (c'est ta propre app).
   Répète pour chaque adresse. (Pour enregistrer des boîtes déjà connectées : `uv run python scripts/register_accounts.py email1 email2 …`.)

## Lancer l'app

```bash
uv run python -m app.bootstrap
```

Puis clique **⟳ Synchroniser** pour récupérer les 12 derniers mois de chaque boîte (réglable). Bascule le thème avec **🎨 Thème**.

## Où sont mes données

- Base + pièces jointes + `runtime.json` : `~/Library/Application Support/Maily/` (macOS), `%APPDATA%/Maily/` (Windows), `~/.local/share/maily/` (Linux).
- Identifiants et jetons : **fichier chiffré local** (`secrets.enc` + `secrets.key`, AES/Fernet, permissions `0600`) dans le dossier ci-dessus - jamais dans le repo, jamais dans le Trousseau. Migration automatique depuis le Trousseau au premier lancement.
- **Déverrouillage Touch ID** au lancement de l'app graphique (macOS ; repli mot de passe de session). Désactivable via `MAILY_NO_BIOMETRIC=1`.
- Confidentialité au repos : repose aussi sur le chiffrement disque de l'OS (FileVault/BitLocker recommandé).

## Accès pour Claude / automatisations

Le cœur (moteur Python + SQLite) est la source de vérité ; l'UI n'en est qu'un client. Une automatisation peut :

- **Lire** : interroger les vues stables `v1_messages` / `v1_threads` / `v1_accounts` dans `app.sqlite`.
- **Agir** : appeler l'API HTTP locale (voir port + `base_url` dans `runtime.json`, jeton d'API dans le Trousseau, à passer en en-tête `Authorization: Bearer …`). Endpoints : `/accounts`, `/messages`, `/threads`, `/search`, `/send`, `/messages/{id}/modify|trash|untrash`, `/accounts/{id}/sync`, etc.
- **Client prêt à l'emploi** : `scripts/claude_client.py` (l'app doit être lancée) lit `runtime.json` + le jeton et expose `accounts()`, `messages()`, `read_message()`, `search()`, `send()`, `modify()`, `trash()`, `sync()`. En ligne de commande :
  ```bash
  uv run python scripts/claude_client.py accounts
  uv run python scripts/claude_client.py inbox --account 1
  uv run python scripts/claude_client.py send --account 1 --to dest@x.co --subject "Coucou" --body "Salut"
  ```
  Pour agir **sans lancer l'app** (headless), Claude peut aussi importer directement le moteur : `from core import accounts_service` puis `sync_account(...)`, `send_from_account(...)`, `modify_message(...)`.
- **Serveur MCP (recommandé pour l'app Claude)** : [`app/mcp_server.py`](app/mcp_server.py) expose Maily comme outils MCP multi-profils à une session Claude tournant sur ce Mac - transport stdio, aucun port réseau. Outils : `maily_list_accounts`, `maily_list_messages`, `maily_get_message`, `maily_search`, `maily_sync`, `maily_send` (chacun avec un paramètre `profile` : email ou nom de profil). Enregistrement dans `claude_desktop_config.json` :
  ```json
  {
    "mcpServers": {
      "maily": {
        "command": "/Users/<toi>/.local/bin/uv",
        "args": ["--directory", "/chemin/vers/fetch-multi-mail-viewer-sender",
                 "run", "--group", "agent", "python", "-m", "app.mcp_server"]
      }
    }
  }
  ```
  Puis redémarrer l'app Claude. (Le MCP lit les secrets chiffrés sans Touch ID : la porte biométrique ne protège que l'app graphique.)

## Développement

```bash
uv run pytest        # 84 tests
```

Architecture : `core/` (moteur : auth, gmail, sync, store, sender, sanitize), `api/` (FastAPI), `app/` (lanceur pywebview), `frontend/` (SPA), `migrations/` (schéma SQLite). Détails dans `docs/superpowers/specs/` et `docs/superpowers/plans/`.

## Distribution

Repo privé : tes amis clonent et **buildent/lancent en local** (chacun fait sa propre configuration Google). Pas de store, pas de signature requise pour un usage local.
