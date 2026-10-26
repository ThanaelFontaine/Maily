# Critical paths (regression check before a release)

What must still work before a version goes out. The QA runs this list on the candidate commit and compares it with the previous version; the verdict is "ready" only when every line has its proof.

| # | Path | How it is checked | Where |
| --- | --- | --- | --- |
| 1 | Test suite | `uv sync --locked && uv run pytest` (macOS and Linux) | `Tests` workflow, or locally |
| 2 | Text check | `python3 scripts/check_text.py` | `Tests` workflow (`check-text`) |
| 3 | Lock file up to date | `uv lock --check` | locally |
| 4 | Start: embedded frontend, migrations, encryption, TLS bundle, local API, window library | `Maily --self-check` | every binary, `Build` workflow |
| 5 | Start: a real window opens and the page loads | `Maily --self-check --window` | macOS, Windows, Linux, and the Linux archive on `ubuntu:24.04`, `debian:trixie`, `fedora:latest` (`Build` workflow) |
| 6 | Reading the mailboxes | `uv run python scripts/demo.py`, then `/accounts`, `/messages`, `/messages/{id}/html`, `/search` with the token of the page | locally, demo data |
| 7 | Google sign-in (OAuth) | the real `InstalledAppFlow` against a local fake token endpoint: authorization URL with PKCE, code exchange, refresh. A real Google test account, when one exists, comes on top | locally |
| 8 | Update check | `core.updates.fetch_latest()` against the real GitHub API with the bundled certifi, then `check(force=True)` | locally, `Maily --tls-selftest` on a binary |
| 9 | Binaries carry the expected dependencies | version of `certifi` in each archive, and the CA bundle has no certificate from `emSign ECC Root CA - G3` | artifacts of the `Build` workflow |
| 10 | Checksums | `shasum -a 256 -c` on every `.sha256` | artifacts of the `Build` workflow |
| 11 | Open security alerts | `gh api repos/ThanaelFontaine/Maily/dependabot/alerts` has no open alert | GitHub |

`Build` does not run on a push to `main`: it runs through `Release` once the version is new. To get the binaries of a `main` that keeps the same version, run it by hand (`gh workflow run build.yml --ref main`); it publishes nothing and keeps the files for 7 days.
