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
- Identifiants et jetons : **Trousseau** de l'OS (jamais dans le repo).
- Confidentialité au repos : repose sur le chiffrement disque de l'OS (FileVault/BitLocker recommandé).

## Accès pour Claude / automatisations

Le cœur (moteur Python + SQLite) est la source de vérité ; l'UI n'en est qu'un client. Une automatisation peut :

- **Lire** : interroger les vues stables `v1_messages` / `v1_threads` / `v1_accounts` dans `app.sqlite`.
- **Agir** : appeler l'API HTTP locale (voir port + `base_url` dans `runtime.json`, jeton d'API dans le Trousseau, à passer en en-tête `Authorization: Bearer …`). Endpoints : `/accounts`, `/messages`, `/threads`, `/search`, `/send`, `/messages/{id}/modify|trash|untrash`, `/accounts/{id}/sync`, etc.

## Développement

```bash
uv run pytest        # 84 tests
```

Architecture : `core/` (moteur : auth, gmail, sync, store, sender, sanitize), `api/` (FastAPI), `app/` (lanceur pywebview), `frontend/` (SPA), `migrations/` (schéma SQLite). Détails dans `docs/superpowers/specs/` et `docs/superpowers/plans/`.

## Distribution

Repo privé : tes amis clonent et **buildent/lancent en local** (chacun fait sa propre configuration Google). Pas de store, pas de signature requise pour un usage local.
