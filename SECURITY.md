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

## Verify a download

Every release from **0.10.0** carries 13 files: the three apps (`.dmg`, `.zip`, `.tar.gz`), the two installers (`install.sh`, `install.ps1`), a `.sha256` file for each of those five, and the three apps again under a name without the version. The CI attests each of the 13 files (a [GitHub artifact attestation](https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/use-artifact-attestations): SLSA build provenance, signed through the OIDC identity of the release workflow and recorded in the public Sigstore log), and releases are immutable: once published, a release and its tag cannot be changed.

With the [GitHub CLI](https://cli.github.com), signed in (`gh auth login`, which `gh attestation verify` requires), from the folder that holds the file:

```bash
gh attestation verify Maily-X.Y.Z-linux-x64.tar.gz --repo ThanaelFontaine/Maily \
  --signer-workflow ThanaelFontaine/Maily/.github/workflows/release.yml \
  --source-ref refs/heads/main --deny-self-hosted-runners
gh release verify-asset vX.Y.Z Maily-X.Y.Z-linux-x64.tar.gz --repo ThanaelFontaine/Maily
```

`install.sh` and `install.ps1` run the first check themselves before installing anything, and stop if it fails. Without `gh`, or with `gh` not signed in, they warn and continue with the checksum only; `MAILY_REQUIRE_ATTESTATION=1` makes them refuse instead. A version older than 0.10.0 has no attestation.

**What the attestation covers:** the file was produced by the `release.yml` workflow of this repository, run from the `main` branch (`--source-ref refs/heads/main`: a file built by that workflow from any other branch, as the dry runs are, is refused) on GitHub-hosted machines (`--deny-self-hosted-runners`), from the commit named in the attestation, and it has not been altered since. Together with the immutable release, it also blocks a swap of the file after publication, which a checksum published in the same place cannot do.

**What it does not cover:** it does not make the code safe (it says where and how the file was built, not that the source is free of bugs; the code is public so that anyone can read it); it does not protect against someone who can change the release workflow or the code on `main`, which is why `main` requires a pull request and passing checks (a branch cannot produce a file that passes the check above); and it is **not an Apple Developer ID or Microsoft code signature**. The apps stay unsigned: macOS and Windows show their warning at first launch, and the steps in the [README](README.md#option-a-download-the-app) still apply. The installer you pipe into a shell is the file served by the latest release: if you want to be sure, download it, read it, and verify it with the same commands before running it.

## Threat model

### What Maily is

A desktop application that runs on your computer, under your user account, and bridges your mailboxes to the AI assistants on that computer. Your mail stays with your provider; Maily stores a synced copy in a local SQLite database and talks only to Google's APIs (Gmail accounts) and to your IMAP server (IMAP accounts). There is no Maily server and no telemetry. Once a day, unless the user turns it off in *Settings > Privacy*, the app asks the public GitHub API for the number of the latest release (`core/updates.py`): GitHub sees the IP address and a `Maily/<version>` user agent, nothing else is sent, and the answer is only compared with the running version. The download page it opens is a fixed URL, never one taken from the answer.

### Assets

1. OAuth tokens and client secret (Gmail access), IMAP passwords.
2. The local API token (full control of Maily while it runs).
3. The content of your mail (database, attachment cache, `.eml` exports).

### What Maily defends against

| Threat | Protection |
|---|---|
| **Another program or user reading secrets on disk** | Secrets are encrypted with Fernet (AES-128-CBC + HMAC-SHA256) in `secrets.enc`; the key is in `secrets.key`; both files, the lock file and `runtime.json` are created with mode `0600`, and the data folder with `0700` (POSIX). Nothing secret is stored in the repository, in `.env`, or in logs (a redaction filter masks tokens and passwords). |
| **Corruption or loss of secrets** | Writes are atomic (temporary file, `fsync`, `os.replace`, `fsync` of the folder), serialized by an inter-process file lock, and the key is created once with `O_EXCL`. If the store cannot be decrypted, Maily raises an error and writes nothing, instead of replacing it with an empty store. |
| **A malicious web page calling the local API** | The API listens on `127.0.0.1` only, on a random port, and requires a bearer token generated at each launch. Requests whose `Host` header is not local are rejected, which blocks DNS-rebinding attacks. The token is never served by a page: the app hands it to its own window in the launch address. |
| **Files written by the MCP tools** | The file name is reduced to one cleaned segment, the folder must be inside Downloads, Desktop or Documents (links followed), an existing file is never overwritten, and new files are created with mode `0600`. |
| **A network attacker between Maily and the IMAP server** | The server certificate and its host name are verified (certificate authorities of the system plus the bundle shipped with Maily); a server whose certificate cannot be verified is refused. |
| **A malicious email (HTML)** | HTML is sanitized with nh3 (Rust `ammonia`): no scripts, event handlers, `javascript:`/`vbscript:`/`data:` links, dangerous CSS (`position`, `url()`, background images). The result is shown in an `<iframe sandbox="">`, without scripts or same-origin access. Links get `rel="noopener noreferrer nofollow"`. |
| **Tracking pixels and remote content** | Remote images and resources are removed by default. The reading pane shows how many were blocked and offers to load them for one message; loading them automatically is an explicit setting. Inline images (`cid:`) and embedded `data:` images are always shown because they do not contact any server; an inline image is shown only if its declared type is a raster format on an allow-list (never SVG). |
| **Prompt injection through email content** | The MCP read tools return the sender, recipients, subject, snippet and bodies of every message inside an `untrusted_email_content` object, with a fixed `notice` saying it is data, never instructions. Bodies are cut at 20,000 characters (text) and 50,000 (HTML), and attachment lists and names are capped too, with `truncated: true`, and text that imitates the envelope key or the notice is broken with a visible character. See [docs/MCP.md](docs/MCP.md#what-the-read-tools-return). |
| **Someone using your unlocked session to open the app** | On macOS, the desktop window can require Touch ID (or the session password) at launch. |
| **Mail left on the disk after you disconnect an account** | *Disconnect* deletes the account's secrets, its messages and the cached attachment files (only inside Maily's own `attachments` folder, links never followed). The database runs with SQLite `secure_delete`, so deleted text is overwritten with zeros in `app.sqlite` instead of staying in free pages; the full-text index is purged the same way (FTS5 `secure-delete`, SQLite 3.42 or later, which `Maily --self-check` requires; otherwise the index is rebuilt), and the write-ahead log (`app.sqlite-wal`) is folded in and truncated. Mail deleted by an earlier version may still sit in free pages of an older database file. |
| **Destructive mistakes** | Gmail permissions are limited to `gmail.modify` and `gmail.send`: Maily can move mail to the trash but cannot delete it permanently. Sends go through an idempotent outbox, so a retry never sends twice. |

### What Maily does not defend against

- **Malware or a compromised account running as your user.** It can read both `secrets.enc` and `secrets.key`, the database and `runtime.json` (which holds the token of the running app), and control the app. Encryption at rest protects against casual copies (backups, file sharing, another user), not against code running as you. Keep your system updated and use full-disk encryption (FileVault, BitLocker, LUKS).
- **Local automations you connect.** The MCP server and the scripts read the secrets without Touch ID, by design. Any MCP client you approve has the same access to your mail as you. Only connect clients you trust, and instruct AI agents to confirm before sending or trashing, and to treat email content as data, never as instructions (prompt injection).
- **Prompt injection, even with the marking.** Marking email content as untrusted helps a well-behaved model, but a model can still be fooled by a crafted message: the marking is a signal, not a guarantee. A hostile email can try to make the assistant call `maily_send` or `maily_trash`, or read other mail and pass it on. Keep a confirmation step on those tools in your client (see [docs/MCP.md](docs/MCP.md#3-safety-rules-recommended)).
- **What your AI assistant does with your mail.** When an assistant calls a Maily tool, the result becomes part of your conversation with it, so it is processed by whoever runs the model behind that assistant. Maily cannot control that side.
- **Your Google account and your IMAP provider.** Their security (password, second factor, recovery) is outside Maily.
- **Loading remote images.** Once you choose to load them for a message or globally, the sender can learn that you opened it and see your IP address.
- **Copies of your mail outside Maily's data folder after a disconnection.** *Disconnect* cannot erase Time Machine or other backups, file-system snapshots, files you saved with the MCP tools or exported as `.eml`, the WebKit/WebView cache of the app window, or application logs you kept. On an SSD, overwriting a block does not guarantee the old cell is erased; full-disk encryption (FileVault, BitLocker, LUKS) is what covers that. If the write-ahead log cannot be truncated at that moment (another process holds the database), it is truncated at a later checkpoint.
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
