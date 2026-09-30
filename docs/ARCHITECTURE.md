# Maily architecture

This document explains how Maily is organized, how data flows, and which interfaces are stable. It is written for contributors and for people who want to automate Maily.

## Principles

1. **The engine is the source of truth.** Everything lives in `core/` (Python). The window, the HTTP API, the scripts and the MCP server are all clients of the same engine and the same SQLite database.
2. **Local only.** No Maily server. Network traffic goes to Google's APIs (Gmail accounts) and to your IMAP server, nowhere else. The local API binds to `127.0.0.1`.
3. **Bring your own credentials.** Each user creates their own Google OAuth client; Maily ships none.
4. **Scriptable by design.** A stable SQL schema (`v1_*` views), a token-protected HTTP API and an MCP server.
5. **Safe by default.** Sanitized HTML, remote images blocked, encrypted secrets, reversible actions only.

## Repository layout

```
core/                 the engine (no UI code)
  paths.py            data folder per platform, MAILY_DATA_DIR override
  db.py               SQLite connection (WAL), numbered migrations
  store.py            all SQL reads and writes (accounts, messages, labels, attachments, outbox, sync state)
  auth.py             Google OAuth: installed-app flow on 127.0.0.1, token refresh
  gmail.py            thin Gmail API client + message parsing (MIME, charsets, attachments)
  sync.py             Gmail sync: bounded backfill, then incremental via the History API, quota retries
  imap_client.py      IMAP over TLS (imaplib): folders, fetch, move to trash
  imap_sync.py        IMAP sync: every folder, no date limit, UIDVALIDITY tracking
  rfc822_parse.py     raw RFC 822 parsing (IMAP messages, .eml export, attachments)
  mime.py, sender.py  building and sending messages (Gmail), idempotent outbox
  accounts_service.py high-level operations used by every client (add/remove account, sync, send, modify, trash, attachments, .eml)
  auto_sync.py        background sync of every account while the app is open
  sanitize.py         HTML sanitization (nh3) and remote-resource blocking
  secret_file.py      encrypted secret store (secrets.enc + secrets.key)
  secrets_store.py    typed helpers on top of secret_file (OAuth client, tokens, IMAP credentials)
  runtime.py          local API token and runtime.json
  biometric.py        Touch ID gate at launch (macOS, LocalAuthentication)
  logging_setup.py    rotating log file with secret redaction
  config.py           settings from MAILY_* environment variables or .env
api/app.py            FastAPI app: the local HTTP API + static frontend
app/bootstrap.py      desktop launcher: data folder, secrets, Touch ID, API server, auto sync, pywebview window
app/mcp_server.py     MCP server over stdio (FastMCP)
frontend/             index.html, app.js, styles.css: plain HTML/CSS/JS, no build step
migrations/           numbered SQL migrations (PRAGMA user_version)
scripts/              command-line helpers (OAuth client import, connect account, API client, demo mode, contrast audit, macOS build)
packaging/            PyInstaller spec and icons
tests/                pytest suite (network and real data never used)
```

## What happens at launch

`uv run python -m app.bootstrap` (or the packaged app) runs `app.bootstrap.run()`:

1. **Data folder.** `core.paths.runtime_dir()` picks `--data-dir` / `MAILY_DATA_DIR` if set, else the platform folder. `ensure_runtime_dirs()` creates it with `attachments/` and `logs/`, permissions `0700` on POSIX.
2. **Logs** go to `logs/maily.log` (1 MB, 3 rotations). A filter redacts tokens, passwords and long base64 strings.
3. **Database.** `core.db.Database` opens `app.sqlite` in WAL mode and applies pending migrations.
4. **Secrets.** A one-time migration imports old entries from the system keyring into `secrets.enc` (earlier versions used the macOS Keychain). Then, on macOS, the **Touch ID gate** runs (skipped if no biometric hardware, or with `MAILY_NO_BIOMETRIC=1`). If Touch ID fails or is cancelled, the app quits.
5. **API token.** A random token (`secrets.token_urlsafe(32)`) is created once and kept in `secrets.enc`. If the secret store cannot be read, Maily stops with a clear message and writes nothing.
6. **Local API.** FastAPI is started by uvicorn in a thread, on `127.0.0.1` and a free random port. When `/health` answers, `runtime.json` is written (`0600`) with `host`, `port`, `base_url`, `schema_version` and `token`.
7. **Auto sync.** A background thread syncs every account at startup and then every `MAILY_POLL_INTERVAL_SECONDS` (180 s, minimum 60 s). A single lock is shared with the Sync button, so two syncs never overlap. Each pass records `last_sync_at` and `last_sync_error` in `sync_state`.
8. **Window.** pywebview opens the page served by the local API. The API injects the token into the page (`window.MAILY_TOKEN`). On macOS, the window is transparent with native vibrancy (used by the Glassmorphism theme); other themes paint an opaque background.

## Data model

Schema in `migrations/`. Main tables:

| Table | Role |
|---|---|
| `accounts` | One row per mailbox: email, display name, color, provider (`gmail` or `imap`), status |
| `messages` | Messages: headers, snippet, text and HTML bodies, `internal_date` (ms), `label_ids` (JSON), unread/starred/trashed flags |
| `threads` | Gmail threads |
| `labels` | Gmail labels, or IMAP folders presented as labels |
| `attachments` | Attachment metadata, `content_id` for inline images, `local_path` once downloaded |
| `outbox` | Outgoing messages with an idempotency key (a retried send is never sent twice) |
| `sync_state` | Per-account key/value: Gmail `last_history_id`, `backfill_done`, IMAP UIDVALIDITY and last UID per folder, `last_sync_at`, `last_sync_error` |
| `messages_fts` | FTS5 full-text index on subject, body and sender, kept up to date by triggers |

### Stable views (public interface)

The `v1_*` views are the **supported way** to read the database from outside. Their columns will not change within schema version 1 (`schema_version` in `runtime.json`):

- `v1_accounts(id, email, display_name, status, last_sync_at)`
- `v1_messages(id, account_id, gmail_id, thread_id, direction, addr_from, addr_to, addr_cc, subject, snippet, body_text, internal_date, is_unread, is_starred, has_attachments, is_trashed)`, trashed messages excluded
- `v1_threads(id, account_id, gmail_thread_id, subject, last_message_at, message_count)`

Open the database **read-only** from other programs; writes must go through the engine (API, MCP or `core.accounts_service`), which keeps Gmail and the local copy consistent.

### IMAP mapping

IMAP messages reuse the Gmail-shaped schema:

- `gmail_id` = `folder \x1f uidvalidity \x1f uid` (unique per folder, parsed back by `imap_client.parse_imap_key`)
- `label_ids` = the folder name, plus `UNREAD` when `\Seen` is absent; `INBOX` keeps the `INBOX` label
- `thread_id` = the `Message-ID` header (IMAP has no threads)

Marking as read or archiving an IMAP message is applied locally only; trash moves the message on the server.

## Synchronization

- **Gmail, first sync:** a bounded backfill (`newer_than:<MAILY_BACKFILL_MONTHS>m`, 12 months by default), then `backfill_done` is set.
- **Gmail, next syncs:** incremental, from the last `historyId` (Gmail History API). If the history is too old (HTTP 404), Maily falls back to a backfill. Per-minute quota errors are retried, and progress is saved as it goes so an interrupted sync resumes where it stopped.
- **Labels** are refreshed at each Gmail sync.
- **IMAP:** every folder (`LIST`), all messages (`SEARCH ALL`), then only new UIDs; a UIDVALIDITY change triggers a re-import of that folder.

## Sending

`accounts_service.send_from_account()` builds a MIME message (`core/mime.py`, attachments included, 25 MB total limit), records it in `outbox` with an idempotency key, then sends it with the Gmail API (`users.messages.send`, threaded with `In-Reply-To` and the Gmail thread id for replies). Sending is Gmail only.

## Security design

See [SECURITY.md](../SECURITY.md) for the threat model. Key mechanisms:

- **Secret store** (`core/secret_file.py`): one JSON document encrypted with Fernet in `secrets.enc`, key in `secrets.key`.
  - Atomic writes: temporary `0600` file in the same folder, `fsync`, `os.replace`, then `fsync` of the folder.
  - The key is created once with `O_CREAT | O_EXCL` and mode `0600`, never overwritten.
  - Every read-modify-write holds an exclusive lock on `secrets.lock` (`fcntl.flock` on POSIX, `msvcrt.locking` on Windows) plus a thread lock, because the app, the MCP server and scripts may run at the same time.
  - A store that cannot be decrypted, or a missing key next to existing secrets, raises `SecretStoreError`: nothing is written, so tokens are never silently erased.
- **Local API guard:** every endpoint except `/health` requires `Authorization: Bearer <token>`, and requests whose `Host` header is not `127.0.0.1`, `localhost` or `[::1]` are rejected (DNS rebinding protection).
- **HTML:** `core/sanitize.py` uses nh3 with an allow-list of tags, attributes and CSS properties (no `position`, no `background` images, no `url()`), strips `javascript:`, `vbscript:` and `data:` links, and removes every remote resource unless remote content is allowed. The frontend then renders the result in an `<iframe sandbox="">` (no scripts, no same-origin access).

## Local HTTP API

Base URL and token: `runtime.json` in the data folder. All endpoints except `/health` need `Authorization: Bearer <token>`.

| Method and path | Purpose |
|---|---|
| `GET /health` | Liveness check (no token) |
| `GET /about` | Version and data folder |
| `GET /accounts` | Accounts |
| `POST /accounts/google` | Add a Google account (opens the browser for consent) |
| `POST /accounts/imap` | Add an IMAP account `{email, password, host, port}` |
| `PATCH /accounts/{id}` | Change `display_name` and/or `color` (`#rrggbb`) |
| `DELETE /accounts/{id}` | Disconnect: delete the account's secrets and local copy |
| `GET /accounts/{id}/labels` | Labels / folders |
| `POST /accounts/{id}/sync` | Sync one account now |
| `GET /messages` | List: `account_id`, `category` (`primary`, `promotions`, `social`, `updates`, `forums`), `label`, `archived`, `trashed`, `limit`, `offset` |
| `GET /messages/{id}` | One message (all columns) |
| `GET /messages/{id}/html` | Sanitized HTML body; `allow_remote=true` keeps remote images. Header `X-Maily-Blocked-Remote` gives the number of blocked resources |
| `GET /messages/{id}/eml` | Raw message as `.eml` |
| `GET /messages/{id}/attachments` | Attachment list |
| `GET /messages/{id}/attachments/{att_id}/download` | Attachment content |
| `POST /messages/{id}/modify` | `{add_labels, remove_labels}` (for example remove `UNREAD` or `INBOX`) |
| `POST /messages/{id}/trash` and `/untrash` | Move to / restore from trash |
| `GET /threads`, `GET /threads/{thread_id}` | Threads |
| `GET /search?q=...` | Full-text search (`account_id`, `limit` optional) |
| `POST /send` | `{account_id, to, subject, body_text, body_html?, cc?, in_reply_to?, thread_id?, attachments?: [{filename, mime_type, data (base64)}], idempotency_key?}` |
| `GET /glass`, `POST /glass` | Glassmorphism blur density (macOS) |

The API is an internal interface of the app first: prefer the `v1_*` views for reading and `scripts/claude_client.py` for acting, which are kept compatible.

## MCP server

`app/mcp_server.py` imports the engine directly (same database, same secrets), runs over stdio and needs neither the app nor a network port. Tools and usage: [docs/MCP.md](MCP.md).

## Frontend

Plain HTML, CSS and JavaScript in `frontend/`, served by the API under `/static`. No framework and no build step.

- `app.js` keeps a small `state` object and re-renders the rail, the list and the reading pane with DOM calls. All text coming from mail is escaped (`esc()`) or set with `textContent`.
- Themes are CSS rules scoped by `:root[data-theme="..."]`: `classic` (default), `aero`, `glass`, `dedsec`. The Classic theme is built on `--c-*` variables; its dark variant only redefines them, either through `prefers-color-scheme: dark` (mode *Automatique*) or through `data-mode="dark"` on `<html>`.
- Preferences (`maily_theme`, `maily_classic_mode`, `maily_remote_images`, `maily_list_width`) are kept in the webview's `localStorage`, which pywebview persists in `<data folder>/webview/`.

## Tests

`uv run pytest` runs the whole suite. `tests/conftest.py` gives every test a temporary data folder (`MAILY_DATA_DIR`), a null keyring backend and disables Touch ID, so the tests never touch real data, real secrets or the system keychain. Gmail and IMAP are replaced by fakes. The GUI contrast audit (`tests/test_contrast.py`) only runs with `MAILY_GUI_TESTS=1` on macOS.

## Versioning and releases

The version lives in `pyproject.toml` and `core/__init__.py` (a test checks they match, and that `CHANGELOG.md` has a section for it). After every successful run of the `Tests` workflow on a push to `main`, `.github/workflows/release.yml` checks whether tag `vX.Y.Z` exists; if not, it creates the tag and a GitHub release whose notes are the matching `CHANGELOG.md` section.
