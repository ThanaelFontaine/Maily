# Contributing to Maily

Thank you for your interest in Maily! Bug reports, ideas, documentation fixes, translations and code are all welcome. This guide explains how to get started.

By contributing, you agree that your contributions are released under the [MIT License](LICENSE), and you agree to follow the [code of conduct](CODE_OF_CONDUCT.md).

## Ways to help

- **Report a bug:** open an issue with what you did, what you expected, what happened, your OS and Maily version (*Réglages > À propos*). Attach logs from the `logs/` folder of your data folder if useful, **after removing any personal data**.
- **Suggest a feature:** open an issue describing the need first, before writing code, so we can agree on the approach.
- **Security issue:** do **not** open a public issue, see [SECURITY.md](SECURITY.md).
- **Good first contributions:** English translation of the interface (it is in French today), SMTP sending for IMAP accounts, Linux and Windows testing, accessibility improvements.

## Development setup

Requirements: [uv](https://docs.astral.sh/uv/) and git (see the README).

```bash
git clone https://github.com/ThanaelFontaine/fetch-multi-mail-viewer-sender.git maily
cd maily
uv sync                           # Python 3.12 + dependencies + dev tools (pytest, httpx)
uv run pytest                     # run the tests
uv run python scripts/demo.py     # the interface on fictitious data, no Google account needed
```

The demo mode is the easiest way to work on the interface: it serves `frontend/` on `127.0.0.1` with a fictitious database in a temporary folder. The frontend has no build step: edit `frontend/index.html`, `app.js` or `styles.css` and reload the page.

To run the real app on a separate, disposable data folder:

```bash
uv run python -m app.bootstrap --data-dir /tmp/maily-dev
```

## Project layout

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). In short: `core/` is the engine (no UI code), `api/` the local HTTP API, `app/` the desktop launcher and the MCP server, `frontend/` the interface, `migrations/` the SQL schema, `tests/` the test suite.

## Rules for changes

- **Tests.** Every change comes with tests, and `uv run pytest` must pass. Tests never use the network, a real mailbox, the real data folder or the system keychain: `tests/conftest.py` provides a temporary `MAILY_DATA_DIR` and a null keyring automatically; use fakes for Gmail and IMAP (see existing tests).
- **No personal data.** Addresses in code, tests, fixtures, docs and screenshots use `example.com`, `example.org` or `example.net`. Never commit tokens, `client_secret*.json`, `secrets.*`, `runtime.json` or a database (they are in `.gitignore`).
- **Security-sensitive code** (`core/secret_file.py`, `core/sanitize.py`, `api/app.py` guard, `core/auth.py`) deserves extra care and explicit tests. Email content is untrusted: always sanitize it and render it in the sandboxed iframe.
- **Database schema.** Changes go in a new numbered file in `migrations/` (`0003_...sql`); never edit an existing migration. The `v1_*` views are a public interface: do not change their columns; add a `v2_*` view if needed.
- **Frontend.** Keep it dependency-free. Escape any text coming from mail (`esc()` or `textContent`). New UI must work in the four themes; check contrast (WCAG AA: 4.5:1 for text). Screenshots for the README are produced with the demo mode.
- **Style.** Python 3.12, standard library first, small functions, clear names. Code comments are in French in the existing code base; English is welcome for new code. Keep the existing formatting.
- **Commits.** One logical change per commit, with a message that says what changes and why.
- **Typography.** Do not use the em dash (U+2014) or en dash (U+2013) anywhere (code, docs, commit messages): use a colon, a comma, parentheses or a plain hyphen instead.

## Pull requests

1. Fork the repository and create a branch from `main`.
2. Make your change with tests, and update the documentation (README, `docs/`) if behavior changes.
3. Add a line to the `## [Unreleased]` section of [CHANGELOG.md](CHANGELOG.md).
4. Run `uv run pytest`.
5. Open the pull request, describing what changes, why, and how you tested it (screenshots for UI changes).

The CI (`.github/workflows/tests.yml`) runs the tests on macOS and Linux for every push and pull request.

## Releasing a version

Maintainers only. Every version has a GitHub release created by the CI, with notes that describe what changed.

1. Choose the version number ([Semantic Versioning](https://semver.org/): while in `0.x`, a new feature bumps the minor number, a fix bumps the patch number).
2. Update `version` in `pyproject.toml` **and** `__version__` in `core/__init__.py` (a test checks they match).
3. In `CHANGELOG.md`, rename `## [Unreleased]` to `## [X.Y.Z] - YYYY-MM-DD`, detail the changes, and add a new empty `## [Unreleased]` section above it (a test checks that the section exists).
4. Merge into `main`. Once the `Tests` workflow is green on `main`, the `Release` workflow creates the tag `vX.Y.Z` and the GitHub release, using that CHANGELOG section as notes. Never create tags or releases by hand.
