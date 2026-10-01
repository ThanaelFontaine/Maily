# Changelog

All notable changes to Maily are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and Maily uses [Semantic Versioning](https://semver.org/). Each version below has a matching GitHub release, created automatically by the CI with the section of this file as its notes.

## [Unreleased]

## [0.8.0] - 2026-10-01

Maily now installs like a real app on every system: a disk image on macOS that asks you to drag Maily into Applications, a ready-to-run folder on Windows and an archive with a desktop entry on Linux. Each one is built and opened by the CI before a release is published. The product page and the documentation now describe Maily as what it is: a bridge from your mailboxes to your assistants.

### Added

- **macOS disk image.** Releases carry `Maily-X.Y.Z-macos-arm64.dmg` instead of a zip. Opening it shows a *Maily* volume with Maily next to an *Applications* shortcut, on a background (1x and Retina 2x) with an arrow, "Drag Maily to Applications" and a line about the first launch of an unsigned app. It is built by `scripts/build_dmg.sh` with [dmgbuild](https://github.com/dmgbuild/dmgbuild) (MIT), which writes the Finder layout without driving Finder; the script checks the image, mounts it read-only to check its content, and writes the `.sha256` file. It installs nothing. It needs `uv` and the build group (`uv sync --group build`).
- **Windows download.** `Maily-X.Y.Z-windows-x64.zip` holds a `Maily` folder with `Maily.exe` (with the Maily icon). It needs the Microsoft Edge WebView2 Runtime, part of Windows 11.
- **Linux download.** `Maily-X.Y.Z-linux-x64.tar.gz` holds a `Maily` folder with the `maily` binary, `maily.desktop`, a 512 x 512 icon and `INSTALL.txt`. The window uses the system's GTK 3 and WebKitGTK 4.1 (not embedded, so that WebKit's helper processes always match their library); the packages to install are listed for Debian, Ubuntu, Fedora and Arch. Built on Ubuntu 24.04 (glibc 2.39 or newer).
- **`--version` and `--self-check`.** `Maily --version` prints the version. `Maily --self-check` checks a built binary without touching the real data folder: embedded frontend and migrations, a database created from the migrations, encryption, TLS bundle, local API and window library; `--window` also opens a real window on a throwaway database and checks that the interface loads, and `--report FILE` writes the result to a file (a windowed Windows program has no console).
- New `linux-gui` dependency group (`uv sync --group linux-gui`) with PyGObject, for running from source on Linux.
- A new `Build` workflow (`.github/workflows/build.yml`) builds the three downloads, each with its `.sha256`, and runs every binary with `--self-check --window`: on macOS (after the `arm64` and version checks), on Windows, on Ubuntu under Xvfb, and the Linux archive again on clean Debian 13 and Fedora containers with only the documented packages. It runs for releases, on any other branch that touches the packaging, and by hand.
- `scripts/release_notes.py assets X.Y.Z` lists the six files every release must carry.

### Changed

- **The release waits for all three systems.** The `Release` workflow calls the `Build` workflow and publishes the tag and the release only when the macOS, Windows and Linux builds all succeeded: the draft release gets the six files, then is published. A published release that lacks some of them only gets the missing ones when the workflow runs again.
- **Install documentation for every system** in the README: download, checksum, first launch (Apple's *Open Anyway* steps, and Control-click > *Open* on macOS 12 to 14 only; SmartScreen's *More info* > *Run anyway* on Windows), prerequisites, updates, and from source with `uv sync` then `uv run maily`. `docs/BUILD.md` explains how each download is built, what differs between systems, and the release pipeline.
- **Maily is described as a bridge.** The README, the documentation, the package description and the product page now say what Maily is: one app on your computer that connects to all your mailboxes and gives every assistant on that computer one local MCP access to all of them. Your mail stays with your provider; Maily keeps a synced copy for speed and search. A new FAQ entry answers "Does my mail stay on my computer?" honestly.
- *Settings > About* says the same in the five languages: your mail stays with your provider, and the folder shown holds Maily's synced copy, the database and the attachments (instead of "Everything stays on this computer").
- **Product page.** Sharp 2x screenshots in AVIF and WebP, with a full-size view; light animations that respect the reduced motion setting; install cards for macOS, Windows and Linux; and the bridge positioning (every assistant, every mailbox).

### Fixed

- A windowed binary on Windows starts with no standard output, which would have made uvicorn's log formatter fail (`sys.stdout.isatty()` on `None`) and kept the local server from starting: the launcher now points the missing streams to the null device.

## [0.7.0] - 2026-10-01

Maily now speaks five languages, its hacker-style theme has an original name, everything in the repository is in English, it starts with `uv run maily`, and every release comes with a downloadable macOS app.

### Added

- **The interface is available in five languages: English (the default), French, German, Spanish and Portuguese.** Every text of the window goes through a small dependency-free translation layer (`frontend/i18n.js`, one JSON file per language in `frontend/i18n/`, keys in English): menus, buttons, tooltips, accessible names (`aria-label`), placeholders, confirmations, notifications, empty states, error messages, the Settings panel and the add-account flows.
- **Language choice.** On first launch, Maily follows the language of the system (or of the browser in demo mode) when it is one of the five, and English otherwise. A new *Language* tab in Settings lists the languages by their native names (English, Français, Deutsch, Español, Português); the choice applies at once, is stored in `prefs.json` like the theme (new `language` preference, `GET/POST /prefs`), and is kept between launches. `<html lang>` follows the active language.
- Replies and forwards always start their subject with `Re:` and `Fwd:`, whatever the interface language, so that every mail client understands them; prefixes already written by other clients (`AW:`, `Tr:`, `WG:`, `RV:`, `Enc:`, ...) are kept as they are. The quoted header lines of the body follow the interface language.
- Changing the language loads the new translation first: if it cannot be loaded, the interface keeps its language and nothing is saved, and when several languages are clicked quickly, the last one wins. Every visible text follows at once, including notifications, form messages, the empty reading pane and the density percentage, and the open message keeps its *Show images* choice.
- **Dates, times, sizes and percentages** are formatted with `Intl` in the active language (the French format was hard-coded). Plurals follow the rules of each language (`Intl.PluralRules`).
- **Stable error codes.** Every API error now carries a code in the `X-Maily-Error` header (`account_not_found`, `imap_login_failed`, `auth_timeout`, `provider_error`, ...) that the interface translates; the `detail` text is in English and only goes to logs and scripts.
- **`uv run maily`** launches the app from a clone: a `maily` console script is declared in `pyproject.toml` (`[project.scripts]`, pointing at `app.bootstrap:main`). `uv run python -m app.bootstrap` still works, with the same `--data-dir` option.
- **Downloadable macOS app.** The release workflow now builds `Maily.app` with PyInstaller on a macOS Apple Silicon runner (it fails if the app is not `arm64`), then creates the tag and a draft release with `Maily-X.Y.Z-macos-arm64.zip` and its `.sha256` checksum file, and publishes it last: a release is never visible without its macOS app, and running the workflow again after a failure resumes safely. Version and notes come from `scripts/release_notes.py`. The app is not signed nor notarized: `docs/BUILD.md` explains what macOS says and how to open it.
- Tests for the translations (every language has exactly the keys of English, with the same placeholders and no em or en dash; every key used by the interface exists; every API error code is translated), for the language preference, for the theme migration and for the console script.
- New screenshots: Glassmorphism theme and the *Language* tab of Settings.
- **Product page.** The source of the product page for <https://maily.thanaelfontaine.eu> lives in `site/` (static HTML and CSS, no build step, automatic dark mode); `site/README.md` explains the local preview. It is not deployed yet.

### Changed

- **The dark terminal theme is renamed Zero Day** (id `zeroday`, formerly `dedsec`), with the same look: its former name belonged to a video game brand. The terminal line, class names, animations and documentation no longer refer to it. A saved `dedsec` preference is read as `zeroday` and `prefs.json` is rewritten once with the new id.
- Theme names are in English in every language: *Classic*, *Frutiger Aero*, *Glassmorphism* (instead of *Glassmorphisme*) and *Zero Day*.
- **English everywhere in the repository:** code comments, docstrings, log messages, command-line output of the scripts, error messages, test names, the MCP tool descriptions and results, the demo data and the documentation are now in English. This changelog is rewritten in English, and so are the release notes taken from it. Only the translation files of the interface hold other languages.
- The Touch ID prompt, the startup error window and the MCP server's messages are in English.
- The repository is now `ThanaelFontaine/Maily`: every link points to <https://github.com/ThanaelFontaine/Maily>.
- The demo mode uses English fictitious data (accounts *Personal*, *Work* and *Old address*, labels *Invoices* and *Travel*).
- Every screenshot in `docs/images/` is regenerated from the English interface; `theme-dedsec.png` becomes `theme-zeroday.png`.
- The documentation explains how to add a language and that interface text always goes through a translation key (`CONTRIBUTING.md`, `docs/ARCHITECTURE.md`).
- The default name of a downloaded attachment without a name is `attachment`.

### Fixed

- **IMAP trash could delete a message for good.** When the server had no trash folder that Maily recognised, the message was still flagged `\Deleted` and expunged. Maily now finds the trash folder by its IMAP special-use flag (`\Trash`) or a usual name that really exists (no more substring match), moves or copies the message there, and only flags and expunges after a successful copy (with `UIDPLUS`, that message alone). Without a trash folder it refuses with "no trash folder on this IMAP account" (API code `no_trash_folder`, translated in the interface, also returned by the `maily_trash` MCP tool) and leaves the message untouched. Folder names that are not quoted in `LIST` responses are now read correctly.
- The reading pane no longer offers *Restore* for a trashed IMAP message: the engine refuses to restore IMAP messages, so the button only led to an error. The documentation now says that trash is reversible for Gmail accounts only, that `.env` only sets the `core/config.py` settings (`MAILY_DATA_DIR` and `MAILY_NO_BIOMETRIC` are environment variables only), and which `category` values `maily_list_messages` accepts.
- The blinking caret of the Zero Day terminal line referenced an animation that did not exist; it now blinks (and stays still when the system asks for reduced motion).

### Removed

- `README.fr.md` and the French copies of the guides in `docs/fr/` (the interface itself is translated instead).

## [0.6.0] - 2026-10-01

First open-source release: a new default look, a single settings panel, a hardened secret store, complete documentation and an automated release process.

### Added

- **Classic theme, now the default.** Light, flat and understated, in the spirit of Google's tools: white background, very light grey surfaces, blue accent `#1a73e8`, system font, no glass, light shadows only on floating windows, slightly rounded corners, WCAG AA contrast. It has a **dark variant** of the same design, in three modes: *Automatic* (follows the system), *Light* and *Dark*. Frutiger Aero, Glassmorphism and the dark terminal theme (named Zero Day since 0.7.0) remain available.
- **Settings panel.** One panel with tabs replaces the *Theme* button and the scattered settings: *Appearance* (theme, Classic mode, glass density), *Privacy* (remote images), *Accounts* (name, color, disconnect) and *About* (version, data folder, license). The Escape key closes dialogs.
- **Remote images: blocked by default, with a per-message override.** The API reports how many remote resources were removed (`X-Maily-Blocked-Remote` header) and the reading pane shows *Show images* to load them for that message only.
- **Automatic sync** of every mailbox every 3 minutes while the app is open (`MAILY_POLL_INTERVAL_SECONDS`), sharing a single lock with the Sync button; the last sync time and error of each account are recorded in `sync_state`.
- **Custom data folder:** `MAILY_DATA_DIR` environment variable and `--data-dir` option, for tests, demos or a separate profile.
- **Demo mode:** `scripts/demo.py` runs the interface on fictitious mailboxes, in a temporary folder, with an in-memory API token, and refuses to use the real data folder.
- `GET /about` endpoint (version and data folder).
- **Preferences are now really remembered between launches.** Theme, Classic mode, remote images and list width are stored in `prefs.json` (mode `0600`) in the data folder, through `GET/POST /prefs` (token required), and read when the window starts. They used to live in the webview's `localStorage`, which was lost at every launch because the local API uses a new random port (hence a new origin) each time, and pywebview ignores its storage folder on macOS. Values found in the old `localStorage` are migrated once.
- Settings tabs follow the ARIA tablist pattern: arrow keys, Home and End move between tabs.
- If the secret store is unreadable at launch, the desktop app now shows the explanation in a window (the packaged app has no terminal), in addition to stderr.
- `docs/ACCES_MAILY_MCP.md` is kept as a short page pointing to the new MCP guide, so that existing links keep working.
- The MCP tool `maily_get_message` now lists the message's attachments with their `attachment_id`.
- `runtime.json` now carries the local API token (file created with mode `0600`), so local automations can call the API without reading the secret store.
- Logs are now written to `logs/maily.log` in the data folder (rotating, with secrets redacted); the logging setup existed but was never enabled.
- **Documentation:** README in English and in French, architecture guide, Google Cloud setup guide (English and French), MCP guide (English and French), build guide, `CONTRIBUTING.md`, `SECURITY.md` (private reporting and threat model), `CODE_OF_CONDUCT.md`, this changelog, and screenshots in `docs/images/`.
- **MIT License.**
- **CI:** tests on macOS and Linux for every push to `main` and every pull request; automatic tag and GitHub release on `main` (after green tests) when the version in `pyproject.toml` has no tag yet, with the matching CHANGELOG section as notes.

### Changed

- The IMAP form is generic: *IMAP address*, with Orange as the default server and any other IMAP server possible.
- Dates are shown in the system time zone (the time zone was hard-coded).
- Buttons painted with an account color (*Reply*, *Send*) always use white text, readable in every theme.
- The Windows fallback window background is white, matching the Classic theme.
- The macOS bundle identifier is now `io.github.thanaelfontaine.maily`, and the bundle version is read from the code instead of being hard-coded.
- The Glassmorphism, Aero and dark terminal (now Zero Day) themes style the new settings panel.
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
- The data folder is created with mode `0700` even when the MCP server or a script creates it before the app.
- The local API no longer accepts the `testserver` host outside the test suite.
- The demo mode also refuses any subfolder of the real data folder.

## [0.5.1] - 2026-08-23

### Changed

- IMAP (Orange) imports everything: every IMAP folder (each becomes a label, `INBOX` keeps the inbox view), without date limit, with UIDVALIDITY and last-UID tracking per folder.

## [0.5.0] - 2026-08-23

### Added

- Read-only IMAP accounts (Orange), with login check before saving and encrypted password storage.
- Export any message as `.eml`, from the app and the MCP server.
- Account management: rename, recolor and disconnect an account from the settings (`DELETE /accounts/{id}` removes its secrets and local copy).
- **+ Add account** button and Google account addition from the app (OAuth consent in the system browser).
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
- Themes Frutiger Aero, a dark terminal theme (named Zero Day since 0.7.0) and Glass (native macOS vibrancy), per-account names and colors.
- Local HTTP API with token and host checks, stable `v1_*` SQL views, `runtime.json`, and a ready-made Python client.
- PyInstaller packaging for macOS, Linux and Windows.

[Unreleased]: https://github.com/ThanaelFontaine/Maily/compare/v0.8.0...HEAD
[0.8.0]: https://github.com/ThanaelFontaine/Maily/compare/v0.7.0...v0.8.0
[0.7.0]: https://github.com/ThanaelFontaine/Maily/compare/v0.6.0...v0.7.0
[0.6.0]: https://github.com/ThanaelFontaine/Maily/compare/v0.5.1...v0.6.0
[0.5.1]: https://github.com/ThanaelFontaine/Maily/compare/v0.5.0...v0.5.1
[0.5.0]: https://github.com/ThanaelFontaine/Maily/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/ThanaelFontaine/Maily/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/ThanaelFontaine/Maily/compare/v0.2.1...v0.3.0
[0.2.1]: https://github.com/ThanaelFontaine/Maily/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/ThanaelFontaine/Maily/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/ThanaelFontaine/Maily/releases/tag/v0.1.0
