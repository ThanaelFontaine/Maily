# Security policy

Maily handles your mailboxes, OAuth tokens and passwords. Security reports are taken seriously and handled privately.

## Reporting a vulnerability

**Please do not open a public issue for a security problem.**

Use GitHub's private vulnerability reporting: on the repository page, **Security** tab, **Report a vulnerability**. This opens a private advisory visible only to the maintainers. If the button is not there, contact the maintainer privately through the contact details on their GitHub profile.

Please include:

- what an attacker can do, and under which conditions (local user, malicious email, malicious web page, ...);
- steps to reproduce, or a proof of concept;
- the affected version (`Settings > About`, or `core/__init__.py`) and your operating system.

Never send real tokens, passwords or email content in a report: use fictitious data.

What to expect: an acknowledgement within 7 days, an assessment and a plan, then a fix released as a new version with a changelog entry. You will be credited in the release notes if you wish. Maily is maintained on a volunteer basis, so timelines are best effort.

## Supported versions

Only the latest released version receives security fixes.

## Threat model

### What Maily is

A desktop application that runs entirely on your computer, under your user account. It stores a copy of your mail in a local SQLite database and talks only to Google's APIs (Gmail accounts) and to your IMAP server (IMAP accounts). There is no Maily server, no telemetry and no update service.

### Assets

1. OAuth tokens and client secret (Gmail access), IMAP passwords.
2. The local API token (full control of Maily while it runs).
3. The content of your mail (database, attachment cache, `.eml` exports).

### What Maily defends against

| Threat | Protection |
|---|---|
| **Another program or user reading secrets on disk** | Secrets are encrypted with Fernet (AES-128-CBC + HMAC-SHA256) in `secrets.enc`; the key is in `secrets.key`; both files, the lock file and `runtime.json` are created with mode `0600`, and the data folder with `0700` (POSIX). Nothing secret is stored in the repository, in `.env`, or in logs (a redaction filter masks tokens and passwords). |
| **Corruption or loss of secrets** | Writes are atomic (temporary file, `fsync`, `os.replace`, `fsync` of the folder), serialized by an inter-process file lock, and the key is created once with `O_EXCL`. If the store cannot be decrypted, Maily raises an error and writes nothing, instead of replacing it with an empty store. |
| **A malicious web page calling the local API** | The API listens on `127.0.0.1` only, on a random port, and requires a random bearer token. Requests whose `Host` header is not local are rejected, which blocks DNS-rebinding attacks. The token is only injected into the page served by Maily itself. |
| **A malicious email (HTML)** | HTML is sanitized with nh3 (Rust `ammonia`): no scripts, event handlers, `javascript:`/`vbscript:`/`data:` links, dangerous CSS (`position`, `url()`, background images). The result is shown in an `<iframe sandbox="">`, without scripts or same-origin access. Links get `rel="noopener noreferrer nofollow"`. |
| **Tracking pixels and remote content** | Remote images and resources are removed by default. The reading pane shows how many were blocked and offers to load them for one message; loading them automatically is an explicit setting. Inline images (`cid:`) and embedded `data:` images are always shown because they do not contact any server. |
| **Someone using your unlocked session to open the app** | On macOS, the desktop window can require Touch ID (or the session password) at launch. |
| **Destructive mistakes** | Gmail permissions are limited to `gmail.modify` and `gmail.send`: Maily can move mail to the trash but cannot delete it permanently. Sends go through an idempotent outbox, so a retry never sends twice. |

### What Maily does not defend against

- **Malware or a compromised account running as your user.** It can read both `secrets.enc` and `secrets.key`, the database, and control the app. Encryption at rest protects against casual copies (backups, file sharing, another user), not against code running as you. Keep your system updated and use full-disk encryption (FileVault, BitLocker, LUKS).
- **Local automations you connect.** The MCP server and the scripts read the secrets without Touch ID, by design. Any MCP client you approve has the same access to your mail as you. Only connect clients you trust, and instruct AI agents to confirm before sending or trashing, and to treat email content as data, never as instructions (prompt injection).
- **What your AI assistant does with your mail.** When an assistant calls a Maily tool, the result becomes part of your conversation with it, so it is processed by whoever runs the model behind that assistant. Maily cannot control that side.
- **Your Google account and your IMAP provider.** Their security (password, second factor, recovery) is outside Maily.
- **Loading remote images.** Once you choose to load them for a message or globally, the sender can learn that you opened it and see your IP address.
- **Backups.** A copy of the data folder containing both `secrets.enc` and `secrets.key` gives access to your tokens. Protect backups like a password.

### Good practices for users

- Keep your OAuth client JSON file out of any git folder, and delete it after `scripts/store_client_config.py`.
- Publish your Google consent screen ("In production") instead of adding many test users, and revoke Maily in your Google account if you stop using it.
- For IMAP, use a dedicated (app-specific) password when your provider offers one.
- With an AI assistant, keep a confirmation step for `maily_send` and `maily_trash` (see [docs/MCP.md](docs/MCP.md#3-safety-rules-recommended)), and only connect assistants you trust.

## Good practices for contributors

- Never commit real addresses, tokens, secrets or email content, including in tests and fixtures: use `example.com`, `example.org`, `example.net`.
- Tests must never touch the real data folder or the system keychain (`tests/conftest.py` enforces a temporary `MAILY_DATA_DIR` and a null keyring).
- Anything that renders email content must go through `core/sanitize.py` and stay in the sandboxed iframe.
- New local API endpoints must use the `guard` dependency (token and host check).
