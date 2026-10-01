# Maily

**A local, multi-account email client for Gmail and IMAP. Your mail stays on your computer.**

[Changelog](CHANGELOG.md) · [Security](SECURITY.md) · [Contributing](CONTRIBUTING.md) · MIT License

Maily is a desktop email client that syncs your Gmail / Google Workspace mailboxes (and, read-only, any IMAP mailbox) into a **local SQLite database**, then lets you read, search, sort and send mail from a clean desktop window. There is no Maily server and no third-party cloud: Maily talks directly to Google (or your IMAP server) with **your own** OAuth credentials, and everything it stores is on your disk.

It is also built to be **scripted**: a stable read-only SQL schema, a local HTTP API and a local [MCP](https://modelcontextprotocol.io/) server let your own automations and AI agents (for example Claude Code) read and act on your mail, on your machine.

![Maily with the default Classic theme](docs/images/classic-light.png)

---

## Table of contents

1. [Features](#features)
2. [Screenshots](#screenshots)
3. [How it works, in one minute](#how-it-works-in-one-minute)
4. [Requirements](#requirements)
5. [Installation, step by step](#installation-step-by-step)
6. [Google setup: bring your own credentials](#google-setup-bring-your-own-credentials)
7. [Launching Maily](#launching-maily)
8. [Using Maily](#using-maily)
9. [Where your data lives](#where-your-data-lives)
10. [Security and privacy](#security-and-privacy)
11. [Automations: SQL, HTTP API and MCP](#automations-sql-http-api-and-mcp)
12. [Configuration reference](#configuration-reference)
13. [Troubleshooting](#troubleshooting)
14. [FAQ](#faq)
15. [Development](#development)
16. [License](#license)

---

## Features

- **Several mailboxes, one window.** Gmail and Google Workspace accounts side by side, with a unified inbox and one view per account. Each account gets a name and a color.
- **Gmail categories and labels.** Primary, Promotions, Social and Updates tabs; archive, trash (reversible), your own labels as folders.
- **Read-only IMAP accounts.** Connect an IMAP mailbox (Orange by default, any IMAP server works): every folder is imported, without date limit. Reading, search, attachments, trash and `.eml` export work; sending does not (no SMTP).
- **Safe HTML rendering.** Messages are sanitized (no scripts, no dangerous links, no CSS tricks) and displayed in a sandboxed frame. Inline images (`cid:`) are shown.
- **Tracking pixels blocked by default.** Remote images are not loaded unless you allow them, globally or for one message.
- **Write, reply, forward**, with attachments (Gmail accounts).
- **Local full-text search** (SQLite FTS5) across every account, instant and offline.
- **Mail tabs.** Cmd/Ctrl + click opens a message in its own tab.
- **Automatic sync** every 3 minutes while the app is open, plus a Sync button.
- **Export** any message as a standard `.eml` file.
- **Five languages.** English, French, German, Spanish and Portuguese. Maily follows your system language on first launch and English otherwise; you can change it in *Settings > Language*.
- **Four themes.** *Classic* (default: light, flat, Google-like, with a dark variant), *Frutiger Aero*, *Glassmorphism* (native blurred glass on macOS) and *Zero Day* (dark, terminal style).
- **One Settings panel** for appearance, language, privacy, accounts and app information.
- **Encrypted secrets.** OAuth tokens and IMAP passwords are encrypted at rest, in files only your user can read. On macOS, the app can require Touch ID at launch.
- **Built for automation.** Stable SQL views, a token-protected local HTTP API, a ready-made Python client and a local MCP server.

## Screenshots

| Classic, light | Classic, dark |
|---|---|
| ![Classic light](docs/images/classic-light.png) | ![Classic dark](docs/images/classic-dark.png) |

| Settings: appearance | Settings: language |
|---|---|
| ![Settings, appearance tab](docs/images/settings-appearance.png) | ![Settings, language tab](docs/images/settings-language.png) |

| Settings: privacy | Settings: accounts |
|---|---|
| ![Settings, privacy tab](docs/images/settings-privacy.png) | ![Settings, accounts tab](docs/images/settings-accounts.png) |

| Remote images blocked | Writing a message |
|---|---|
| ![Remote images blocked banner](docs/images/remote-images-blocked.png) | ![Composer](docs/images/composer.png) |

| Frutiger Aero theme | Glassmorphism theme |
|---|---|
| ![Frutiger Aero](docs/images/theme-aero.png) | ![Glassmorphism](docs/images/theme-glass.png) |

| Zero Day theme | |
|---|---|
| ![Zero Day](docs/images/theme-zeroday.png) | |

All screenshots use the built-in [demo mode](#try-it-without-a-google-account) with fictitious data.

## How it works, in one minute

```
 Gmail API / IMAP  <--- sync --->  core/ (Python engine)  --->  app.sqlite (your mail, local)
                                          |
                                          +--> api/  local HTTP API on 127.0.0.1 (random port, token)
                                          |        ^
                                          |        +--- frontend/ (the window you see, via pywebview)
                                          |        +--- your scripts (scripts/claude_client.py)
                                          |
                                          +--> app/mcp_server.py  (MCP over stdio, for AI agents)
```

- The **engine** (`core/`) is the source of truth: it syncs mail, stores it in SQLite, sends mail and manages secrets.
- The **window** is a small web page (`frontend/`) shown by [pywebview](https://pywebview.flowrl.com/) and served by a local API bound to `127.0.0.1` only.
- Your **automations** use the same engine: read the database, call the local API, or use the MCP server.

More detail in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Requirements

- **Operating system:** macOS (Apple Silicon or Intel) is the primary, tested platform. Linux and Windows are expected to work (the code has fallbacks for both) but are less tested; see [docs/BUILD.md](docs/BUILD.md) for their system packages.
- **[uv](https://docs.astral.sh/uv/)**, the Python package manager. It installs the right Python (3.12) and every dependency for you.
- **git**, to download the code.
- **A Google account** and about 10 minutes to create your own free OAuth credentials (only for Gmail accounts; IMAP needs only your mailbox password).

No paid account, no server, no credit card.

## Installation, step by step

### 1. Install uv

macOS and Linux:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Windows (PowerShell):

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Other methods (Homebrew, pipx, ...) are listed in the [uv documentation](https://docs.astral.sh/uv/getting-started/installation/). Open a new terminal afterwards and check with `uv --version`.

### 2. Download Maily

```bash
git clone https://github.com/ThanaelFontaine/Maily.git maily
cd maily
```

### 3. Install Python and the dependencies

```bash
uv python install 3.12
uv sync
```

`uv sync` creates a private virtual environment in `.venv/` inside the project. Nothing is installed system-wide.

### 4. Check that everything works

```bash
uv run pytest
```

All tests should pass. They never touch your real data (each test gets a temporary folder).

### Try it without a Google account

Want to look around first? The demo mode starts the interface on fictitious mailboxes, in a temporary folder, without network access and without touching any real data or secret:

```bash
uv run python scripts/demo.py
```

Open the address it prints (for example `http://127.0.0.1:53817/`) in your browser. Sending and syncing are disabled; marking as read, archiving and trashing only affect the demo database. Press Ctrl+C to stop.

## Google setup: bring your own credentials

Maily uses the "bring your own credentials" model (like rclone or GAM): **you** create a small, free Google Cloud project and an OAuth client of type *Desktop app*. Maily then connects to Gmail on your behalf. Consequences:

- No shared Maily credentials, nothing to trust but Google and your own machine.
- Google shows an "unverified app" screen the first time. This is expected: it is **your** app. Click *Advanced*, then *Go to Maily (unsafe)*.

The full walkthrough, with every screen of the Google Cloud console explained, is in **[docs/GOOGLE_CLOUD_SETUP.md](docs/GOOGLE_CLOUD_SETUP.md)**. In short:

1. Create a Google Cloud project and enable the **Gmail API**.
2. Configure the consent screen: user type **External**, then **Publish app** (in "Testing" mode, Google makes the connection expire after 7 days).
3. Create an OAuth client of type **Desktop app** and download its JSON file.
4. Give that file to Maily (the secret is encrypted, never printed):

   ```bash
   uv run python scripts/store_client_config.py ~/Downloads/client_secret_XXXX.json
   ```

   You can then delete the downloaded JSON file.

5. Add your mailboxes, either from the app (**+ Add account**, at the bottom left, then *Google account*) or from the terminal:

   ```bash
   uv run python scripts/connect_account.py
   ```

   Your browser opens on Google's consent screen. Repeat for each address.

Maily asks for two Gmail permissions: `gmail.modify` (read, label, archive, trash) and `gmail.send` (send). It never permanently deletes a message.

### IMAP accounts (read-only)

In the app: **+ Add account**, then *IMAP address*. Enter the address and the password; the server defaults to Orange (`imap.orange.fr`, port 993, TLS) and can be changed under *IMAP server*. Maily tests the login before saving anything. The password is stored encrypted, like OAuth tokens. Some providers require an "app password" instead of your usual password: check your provider's help pages.

## Launching Maily

From the project folder:

```bash
uv run maily
```

(`uv run python -m app.bootstrap` does the same.)

On macOS, if Touch ID is configured, the system asks you to unlock Maily first (your session password works too). Then the window opens and a first sync starts in the background: the first time, Maily downloads the last 12 months of each Gmail mailbox (configurable) and all IMAP folders. This can take a while for big mailboxes; the list fills in as it goes.

Useful options:

```bash
uv run maily --data-dir /path/to/folder    # use another data folder
MAILY_NO_BIOMETRIC=1 uv run maily          # skip the Touch ID gate
```

Each release also offers a ready-made macOS app for Apple Silicon (`Maily-X.Y.Z-macos-arm64.zip`, unsigned: see [docs/BUILD.md](docs/BUILD.md#downloading-the-macos-app) for how to open it). To build a double-clickable application yourself (`Maily.app`, or an executable on Linux and Windows), see [docs/BUILD.md](docs/BUILD.md).

## Using Maily

The interface is available in English, French, German, Spanish and Portuguese. The labels below are the English ones:

- **Left column:** *All (unified)*, then one entry per account. Click an account's colored dot to change its color. When an account is selected, its folders (*Inbox*, *Archived*, *Trash*) and *Labels* appear below. **+ Add account** is pinned at the bottom.
- **Middle column:** the message list, with Gmail category tabs (*Primary*, *Promotions*, *Social*, *Updates*). The two small buttons are *Sync* and *Mark all as read*. Drag the separator to resize.
- **Right column:** the open message, with *Reply*, forward, download `.eml`, archive and trash. Cmd/Ctrl + click on a message opens it in a tab.
- **Search box** (*Search mail*): full-text search in the local database, across all accounts or the selected one.
- **Compose:** new message. The *Send* button takes the color of the selected sender account.
- **Settings** (gear icon, top right), five tabs:
  - *Appearance:* theme (Classic, Frutiger Aero, Glassmorphism, Zero Day); for Classic, *Automatic* (follows the system), *Light* or *Dark*; for Glassmorphism, the density of the blurred background (macOS).
  - *Language:* English, Français, Deutsch, Español or Português.
  - *Privacy:* load remote images automatically or not (off by default).
  - *Accounts:* display name, color, and *Disconnect* (removes the account's secrets and its local copy of the mail; reconnecting downloads it again).
  - *About:* version, data folder, license.
- **Escape** closes the open dialog.

Your choices are remembered between launches (they are stored in `prefs.json` in the data folder).

## Where your data lives

Everything is in one folder:

| Platform | Default folder |
|---|---|
| macOS | `~/Library/Application Support/Maily/` |
| Windows | `%APPDATA%\Maily\` |
| Linux | `$XDG_DATA_HOME/maily/`, or `~/.local/share/maily/` |

Set `MAILY_DATA_DIR` (or pass `--data-dir`) to use another folder. The folder contains:

| File or folder | Content |
|---|---|
| `app.sqlite` (+ `-wal`, `-shm`) | Your messages, accounts, labels, sync state, full-text index |
| `attachments/` | Attachments you opened (local cache) |
| `secrets.enc` | Encrypted secrets: OAuth client, OAuth tokens, IMAP passwords, local API token |
| `secrets.key` | The key that decrypts `secrets.enc` |
| `secrets.lock` | Lock file that serializes concurrent writes to the secrets |
| `prefs.json` | Interface preferences: theme, Classic mode, remote images, list width, language |
| `runtime.json` | Address, port and API token of the running app (for your scripts) |
| `logs/` | Logs, with tokens and passwords redacted |
| `webview/` | Window storage used by pywebview on some platforms (nothing important) |

The folder and the secret files are readable by your user only (permissions `0700` / `0600` on macOS and Linux). **Back up** this folder if you want to keep your local copy; note that anyone who gets both `secrets.enc` and `secrets.key` can read your tokens, so treat a backup like a password.

To start over, quit Maily and delete the folder. To remove Maily's access on Google's side, visit your Google account's [third-party connections page](https://myaccount.google.com/connections).

## Security and privacy

Short version (details and threat model in [SECURITY.md](SECURITY.md)):

- **Local only.** No Maily server. The local API listens on `127.0.0.1` only, on a random port, requires a random token, and rejects requests whose `Host` is not local (protection against DNS rebinding).
- **Encrypted secrets.** Tokens and passwords are encrypted with Fernet (AES-128-CBC + HMAC-SHA256) in `secrets.enc`; the key is in `secrets.key`; both are `0600`. Writes are atomic and locked across processes, and an unreadable store raises a clear error instead of being silently overwritten. Encryption at rest protects against casual copies; it does not protect against malware running as your user, which could read both files. Full-disk encryption (FileVault, BitLocker, LUKS) is recommended.
- **Touch ID gate** (macOS, optional): the window only opens after Touch ID or your session password. The MCP server and scripts do not ask for it, by design, so that local automations can work.
- **Sanitized HTML.** Messages go through [nh3](https://github.com/messense/nh3) (Rust `ammonia`): no scripts, no `javascript:` or `data:` links, filtered CSS, then a sandboxed iframe.
- **Tracking pixels.** Remote images are blocked by default; a banner tells you how many were blocked and lets you load them for one message.
- **Least privilege on Gmail.** `gmail.modify` and `gmail.send` only; messages go to the trash, never deleted permanently.

Found a vulnerability? Please report it privately, see [SECURITY.md](SECURITY.md).

## Automations: SQL, HTTP API and MCP

Maily is meant to be driven by your own tools. Three levels, from simplest to richest:

### 1. Read the database (no app needed)

Open `app.sqlite` read-only and use the **stable views**, which will keep their columns across versions:

- `v1_accounts` (id, email, display_name, status, last_sync_at)
- `v1_messages` (id, account_id, gmail_id, thread_id, direction, addr_from, addr_to, addr_cc, subject, snippet, body_text, internal_date, is_unread, is_starred, has_attachments, is_trashed), trashed messages excluded
- `v1_threads` (id, account_id, gmail_thread_id, subject, last_message_at, message_count)

```bash
sqlite3 -readonly "$HOME/Library/Application Support/Maily/app.sqlite" \
  "SELECT datetime(internal_date/1000,'unixepoch'), addr_from, subject FROM v1_messages ORDER BY internal_date DESC LIMIT 10;"
```

Tables other than `v1_*` are internal and may change.

### 2. The local HTTP API (app running)

When the app runs, `runtime.json` gives `base_url` and `token`. Every call needs `Authorization: Bearer <token>`. Main endpoints: `GET /accounts`, `GET /messages`, `GET /messages/{id}`, `GET /messages/{id}/html`, `GET /search?q=...`, `POST /send`, `POST /messages/{id}/modify`, `POST /messages/{id}/trash`, `POST /messages/{id}/untrash`, `POST /accounts/{id}/sync`, `GET /messages/{id}/eml`. The full list is in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#local-http-api).

A ready-made client does the plumbing for you:

```bash
uv run python scripts/claude_client.py accounts
uv run python scripts/claude_client.py inbox --account 1
uv run python scripts/claude_client.py read 42
uv run python scripts/claude_client.py send --account 1 --to someone@example.com --subject "Hello" --body "Hi!"
```

It can also be imported: `from scripts.claude_client import accounts, messages, read_message, search, send, sync`.

### 3. The MCP server (for AI agents)

`app/mcp_server.py` exposes Maily as MCP tools over **stdio** (no network port): `maily_list_accounts`, `maily_list_messages`, `maily_get_message`, `maily_search`, `maily_sync`, `maily_send`, `maily_export_eml`, `maily_download_attachment`, `maily_trash`. It works without the app being open.

The repository ships a [`.mcp.json`](.mcp.json): open a Claude Code session in the project folder and approve the `maily` server (or type `/mcp`). For Claude Desktop or another MCP client, and for the recommended safety rules (confirm before sending or trashing), see **[docs/MCP.md](docs/MCP.md)**.

## Configuration reference

Environment variables (or a `.env` file in the folder you launch from, see [`.env.example`](.env.example)):

| Variable | Default | Meaning |
|---|---|---|
| `MAILY_DATA_DIR` | platform folder | Data folder (same as `--data-dir`) |
| `MAILY_POLL_INTERVAL_SECONDS` | `180` | Automatic sync interval while the app is open (minimum 60) |
| `MAILY_BACKFILL_MONTHS` | `12` | Months of Gmail history downloaded by the first sync |
| `MAILY_ATTACHMENT_CACHE_MB` | `500` | Attachment cache size (reserved, not enforced yet) |
| `MAILY_LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING` or `ERROR` |
| `MAILY_NO_BIOMETRIC` | unset | Set to `1` to skip the Touch ID gate |

## Troubleshooting

**"OAuth client credentials (client_id/secret) are missing" when adding a Google account.**
The OAuth client is not stored yet. Run `uv run python scripts/store_client_config.py path/to/client_secret.json`, then try again.

**Google says "Access blocked" or "This app is blocked".**
Check that the consent screen user type is *External* and that the Gmail API is enabled. For a Google Workspace account, the administrator may have to allow the app in the Admin console (*Security > API controls > Manage third-party app access*, by Client ID). See [docs/GOOGLE_CLOUD_SETUP.md](docs/GOOGLE_CLOUD_SETUP.md#troubleshooting).

**I have to reconnect every week.**
Your consent screen is still in *Testing*. Google issues refresh tokens that expire after 7 days in that mode. Publish the app (*Audience > Publish app*), then reconnect the account once.

**"Maily cannot start: Cannot decrypt ..." at launch.**
`secrets.enc` cannot be decrypted with `secrets.key` (the key was replaced, or a file is damaged). Maily stops without modifying anything. Restore both files from a backup if you have one; otherwise delete `secrets.enc` and `secrets.key` and reconnect your accounts (your mail in `app.sqlite` is kept).

**The window stays empty or says it cannot reach the local API.**
Run from a terminal to see the error: `uv run maily`. Check the logs in the `logs/` folder of the data folder.

**Remote images do not show.**
That is the privacy default. Click *Show images* above the message, or enable *Load remote images automatically* in *Settings > Privacy*.

**The Glassmorphism theme is opaque.**
The native blur needs macOS with *System Settings > Accessibility > Display > Reduce transparency* turned off. On Linux and Windows this theme has no native blur.

**Linux: the window does not open.**
pywebview needs GTK and WebKit2GTK (or Qt). Install the packages listed in [docs/BUILD.md](docs/BUILD.md#linux-x86_64).

**The MCP tools do not appear in Claude Code.**
The server must be approved: type `/mcp` in Claude Code. See [docs/MCP.md](docs/MCP.md#troubleshooting).

## FAQ

**Does Maily send my mail anywhere?**
No. It talks only to Google's APIs (for Gmail accounts) and to your IMAP server. There is no Maily server, no analytics, no telemetry.

**Why do I need my own Google Cloud project?**
Gmail's permissions are "restricted" scopes: a shared, public OAuth client would have to go through Google's verification, including a paid third-party security assessment. With your own client, the app is yours, it is free, and nobody else holds credentials to your mail.

**Is my own Google Cloud project free?**
Yes for this use: enabling the Gmail API and creating an OAuth client costs nothing and requires no billing account.

**Can I use a regular @gmail.com address?**
Yes. Gmail and Google Workspace accounts can be mixed. Choose *External* on the consent screen so that all your accounts can connect.

**Why can't I send from an IMAP account?**
IMAP only reads mail. Sending would need SMTP, which Maily does not implement yet. Contributions welcome.

**Can Maily delete my mail for good?**
No. *Trash* moves the message to the trash (reversible, and Gmail empties its trash itself after 30 days). *Disconnect* only removes Maily's local copy and secrets; your mailbox is untouched.

**Does it work offline?**
Reading and searching what is already synced works offline. Sync and sending need a connection.

**Which languages does the interface speak?**
English, French, German, Spanish and Portuguese. Another language is a welcome contribution: add a file in `frontend/i18n/` (see [CONTRIBUTING.md](CONTRIBUTING.md)).

**Can AI agents read my mail?**
Only if you set it up: the MCP server runs only when your MCP client starts it, on your machine. See [docs/MCP.md](docs/MCP.md) for safety rules.

## Development

```bash
uv sync                           # dependencies, including the dev group (pytest, httpx)
uv run pytest                     # the whole test suite
uv run python scripts/demo.py     # the interface on fictitious data
```

The frontend is plain HTML, CSS and JavaScript (no build step): edit `frontend/` and reload. Project layout, conventions and the release process are described in [CONTRIBUTING.md](CONTRIBUTING.md) and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## License

[MIT](LICENSE), © 2026 Thanaël Fontaine.
