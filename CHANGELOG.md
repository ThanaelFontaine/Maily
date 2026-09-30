# Changelog

All notable changes to Maily are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and Maily uses [Semantic Versioning](https://semver.org/). Each version below has a matching GitHub release, created automatically by the CI with the section of this file as its notes.

## [Unreleased]

## [0.6.0] - 2026-09-30

First open-source release: a new default look, a single settings panel, a hardened secret store, complete documentation and an automated release process.

### Added

- **Classic theme, now the default.** Light, flat and understated, in the spirit of Google's tools: white background, very light grey surfaces, blue accent `#1a73e8`, system font, no glass, light shadows only on floating windows, slightly rounded corners, WCAG AA contrast. It has a **dark variant** of the same design, in three modes: *Automatique* (follows the system), *Clair* (light) and *Sombre* (dark). Frutiger Aero, Glassmorphism and DedSec remain available.
- **Settings panel (Réglages).** One panel with tabs replaces the *Theme* button and the scattered settings: *Apparence* (theme, Classic mode, glass density), *Confidentialité* (remote images), *Comptes* (name, color, disconnect) and *À propos* (version, data folder, license). The Escape key closes dialogs.
- **Remote images: blocked by default, with a per-message override.** The API reports how many remote resources were removed (`X-Maily-Blocked-Remote` header) and the reading pane shows *Afficher les images* to load them for that message only.
- **Automatic sync** of every mailbox every 3 minutes while the app is open (`MAILY_POLL_INTERVAL_SECONDS`), sharing a single lock with the Sync button; the last sync time and error of each account are recorded in `sync_state`.
- **Custom data folder:** `MAILY_DATA_DIR` environment variable and `--data-dir` option, for tests, demos or a separate profile.
- **Demo mode:** `scripts/demo.py` runs the interface on fictitious mailboxes, in a temporary folder, with an in-memory API token, and refuses to use the real data folder.
- `GET /about` endpoint (version and data folder).
- The MCP tool `maily_get_message` now lists the message's attachments with their `attachment_id`.
- `runtime.json` now carries the local API token (file created with mode `0600`), so local automations can call the API without reading the secret store.
- Logs are now written to `logs/maily.log` in the data folder (rotating, with secrets redacted); the logging setup existed but was never enabled.
- **Documentation:** English README and French README, architecture guide, Google Cloud setup guide (English and French), MCP guide (English and French), build guide, `CONTRIBUTING.md`, `SECURITY.md` (private reporting and threat model), `CODE_OF_CONDUCT.md`, this changelog, and screenshots in `docs/images/`.
- **MIT License.**
- **CI:** tests on macOS and Linux for every push and pull request; automatic tag and GitHub release on `main` (after green tests) when the version in `pyproject.toml` has no tag yet, with the matching CHANGELOG section as notes.

### Changed

- The IMAP form is generic: *Adresse IMAP*, with Orange as the default server and any other IMAP server possible.
- Dates are shown in the system time zone (the time zone was hard-coded).
- Buttons painted with an account color (*Répondre*, *Envoyer*) always use white text, readable in every theme.
- The Windows fallback window background is white, matching the Classic theme.
- The macOS bundle identifier is now `io.github.thanaelfontaine.maily`, and the bundle version is read from the code instead of being hard-coded.
- The Glassmorphism, Aero and DedSec themes style the new settings panel.
- `.mcp.json` uses `${CLAUDE_PROJECT_DIR:-.}` instead of an absolute path.

### Fixed

- **Security: secret store integrity.** `secrets.enc` was rewritten in place, without any lock between processes, and a decryption error was silently treated as an empty store, so the next write erased every token. Writes are now atomic (temporary `0600` file, `fsync`, `os.replace`, `fsync` of the folder), serialized by an inter-process lock (`fcntl.flock` on POSIX, `msvcrt.locking` on Windows), the key is created once with `O_EXCL` and mode `0600`, and an unreadable store (wrong key, damaged file, missing key next to existing secrets) raises a clear `SecretStoreError` without writing anything. The app stops with an explicit message in that case.
- Gmail sync: per-minute quota errors are retried, and incremental sync keeps its progress when interrupted.
- `runtime.json` permissions are enforced before any token byte is written, and file descriptors are closed exactly once on every error path.
- The remote-images privacy setting documented since 0.1.0 had been lost (images were always loaded); it is back, off by default.

### Removed

- The *Theme* button in the top bar (replaced by the settings panel).
- Internal planning documents that were not useful to users or contributors (`BRIEF_outil_email_local.md`, `docs/superpowers/`), and duplicate files created by iCloud.
- Personal addresses and absolute paths from code, tests and documentation (replaced by `example.com`, `example.org`, `example.net` and generic paths).

### Security

- Tests are isolated from real data: every test gets a temporary data folder, a null keyring backend and the Touch ID gate disabled.

## [0.5.1] - 2026-08-23

### Changed

- IMAP (Orange) imports everything: every IMAP folder (each becomes a label, `INBOX` keeps the inbox view), without date limit, with UIDVALIDITY and last-UID tracking per folder.

## [0.5.0] - 2026-08-23

### Added

- Read-only IMAP accounts (Orange), with login check before saving and encrypted password storage.
- Export any message as `.eml`, from the app and the MCP server.
- Account management: rename, recolor and disconnect an account from the settings (`DELETE /accounts/{id}` removes its secrets and local copy).
- **+ Ajouter un compte** button and Google account addition from the app (OAuth consent in the system browser).
- Banner close button and automatic dismissal after 5 seconds.

### Fixed

- Packaged app: embedded `certifi` CA bundle (TLS error when adding an account), `_cffi_backend` and `anyio` (crash at startup).

## [0.4.0] - 2026-08-20

### Added

- Local MCP server `maily` (stdio) with multi-profile tools for AI agents: list accounts and messages, read, search, sync, send, download attachments, trash.
- `.mcp.json` provided by the repository; `mcp` is a main dependency.

## [0.3.0] - 2026-08-20

### Added

- Secrets moved from the system keychain to a local encrypted file (`secrets.enc` + `secrets.key`, Fernet, `0600`), with automatic one-time migration.
- Touch ID unlock at launch on macOS (session password fallback), `MAILY_NO_BIOMETRIC=1` to disable.

## [0.2.1] - 2026-08-19

### Changed

- The Glass theme adapts to the system light and dark modes.

## [0.2.0] - 2026-08-19

### Added

- App icon and macOS build installed in `/Applications`.

### Fixed

- List/message splitter only resizes while the mouse button is held; Cmd+click opens a tab on the first try; icon buttons with tooltips.
- Read-message dot hidden in every theme; composer legibility in the Glass theme; send button in the account color; glass opacity persisted.

## [0.1.0] - 2026-08-18

### Added

- First version: local multi-account Gmail client with a SQLite database, OAuth "bring your own credentials", bounded backfill and incremental sync.
- Reading with sanitized HTML, inline images, downloadable attachments, remote images blocked by default.
- Sending, replying and forwarding with attachments (25 MB limit).
- Archive, trash, restore, auto mark-as-read, Gmail categories, labels as folders, local full-text search, mail tabs.
- Themes Frutiger Aero, DedSec and Glass (native macOS vibrancy), per-account names and colors.
- Local HTTP API with token and host checks, stable `v1_*` SQL views, `runtime.json`, and a ready-made Python client.
- PyInstaller packaging for macOS, Linux and Windows.

[Unreleased]: https://github.com/ThanaelFontaine/fetch-multi-mail-viewer-sender/compare/v0.6.0...HEAD
[0.6.0]: https://github.com/ThanaelFontaine/fetch-multi-mail-viewer-sender/compare/v0.5.1...v0.6.0
[0.5.1]: https://github.com/ThanaelFontaine/fetch-multi-mail-viewer-sender/compare/v0.5.0...v0.5.1
[0.5.0]: https://github.com/ThanaelFontaine/fetch-multi-mail-viewer-sender/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/ThanaelFontaine/fetch-multi-mail-viewer-sender/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/ThanaelFontaine/fetch-multi-mail-viewer-sender/compare/v0.2.1...v0.3.0
[0.2.1]: https://github.com/ThanaelFontaine/fetch-multi-mail-viewer-sender/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/ThanaelFontaine/fetch-multi-mail-viewer-sender/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/ThanaelFontaine/fetch-multi-mail-viewer-sender/releases/tag/v0.1.0
