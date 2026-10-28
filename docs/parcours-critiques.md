# Critical user journeys

The journeys that must keep working for a person using Maily (local app, local API, MCP server), with how to run each one by hand, what to expect, and what runs them automatically. Use it as the non-regression checklist before a release.

- Last verified: 2026-10-28
- Commit of `origin/main` verified: `c4843e062e2c46c89dcf735ca50363efb451f3d9` (version 0.9.1)
- Environment: macOS, Python 3.12 from `uv sync --locked`, everything local, fictitious data only (demo mode), no real mailbox, no network to a provider.
- "Automated" results marked "suite" come from the full `uv run pytest` run of the same day on that commit (green), not re-run for this page.

## P1. Start the app and the local API on demo data

- **Proves:** the local API starts, serves the interface, and refuses requests without the token.
- **Run:**
  ```bash
  uv run python scripts/demo.py --port 8765 --data-dir /tmp/maily-demo
  curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8765/health            # 200
  curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8765/accounts          # 401, no token
  ```
  The token is injected into the served page (`window.MAILY_TOKEN`); send it as `Authorization: Bearer <token>`. `GET /accounts` then returns the three fictitious accounts.
- **Expected:** 200, then 401 without token, then 3 accounts (`example.com`, `example.org`, `example.net`).
- **Automated:** `tests/test_api.py`, `tests/test_api_static.py` (`test_index_injects_token`, `test_static_served`), `tests/test_demo.py` (the demo refuses the real data folder).
- **Result 2026-10-28:** green (manual: 200, 401, 3 accounts; suite green).

## P2. List and read messages

- **Proves:** the unified inbox, one account, a full message, its sanitized HTML and its attachments.
- **Run:** with the token of P1: `GET /messages?limit=100`, `GET /messages?account_id=2`, `GET /messages/1`, `GET /messages/1/html`, `GET /messages/1/attachments`, `GET /messages/1/attachments/1/download`.
- **Expected:** 9 inbox messages in the unified view, 2 for account 2; the message has its subject and body; the HTML answer carries `X-Maily-Blocked-Remote: 0` and no script; the attachment list holds `meeting-minutes.pdf`; the download returns the demo file.
- **Automated:** `tests/test_store_listing.py`, `tests/test_api_v2.py`, `tests/test_sanitize.py`, `tests/test_attachments.py`.
- **Result 2026-10-28:** green (manual: 9, 2, subject read, HTML 200, attachment listed and downloaded; suite green).

## P3. Actions on a message: archive, trash, restore

- **Proves:** the reading-pane actions change the local state and are reversible.
- **Run:** with the token: `POST /messages/1/modify` with `{"remove_labels":["INBOX"]}` (archive), then `GET /messages?archived=true`; `POST /messages/1/modify` with `{"add_labels":["INBOX"]}`; `POST /messages/2/trash`, `GET /messages?trashed=true`, `POST /messages/2/untrash`.
- **Expected:** each call answers `{"ok":true}`; the inbox drops from 9 to 8 after the archive and returns to 9; the trash holds message 2, then is empty after the restore.
- **Automated:** `tests/test_actions.py`, `tests/test_accounts_service.py` (`test_trash_message_imap`), `tests/test_sync_labels.py`.
- **Result 2026-10-28:** green (manual as above; suite green).

## P4. Search

- **Proves:** local full-text search across accounts, empty result for an unknown word.
- **Run:** `GET /search?q=meeting`, then `GET /search?q=zzzqqq` (with the token).
- **Expected:** two results ("Thursday's progress meeting", "General meeting on October 12"), then an empty list.
- **Automated:** `tests/test_store.py`, `tests/test_api.py`.
- **Result 2026-10-28:** green (manual: 2 results then 0; suite green).

## P5. The web interface in a real browser

- **Proves:** the page served by FastAPI loads, lists mail, opens a message, runs archive, trash and restore from the buttons, searches and opens Settings, without a script error.
- **Run:** start the demo (P1), open `http://127.0.0.1:8765/` in a headless Chromium (Playwright), then: select the first account, open the first message, click *Archive*, open *Archived*, trash a message, open *Trash*, click *Restore*, type `meeting` in the search box, open *Settings* then *About*. Watch the page console.
- **Expected:** the message list appears; opening a message shows its subject in the reading pane and a sandboxed frame; the lists follow each action (the archived message leaves the inbox and shows in *Archived*, the trashed one shows in *Trash* and leaves it after *Restore*); the search shows the matching row; *About* shows `Version 0.9.1` and the demo data folder; no console or page error.
- **Automated:** none for the browser flow (the API behind it is covered by P1 to P4; `tests/test_frontend_defaults.py` and `tests/test_i18n.py` cover the static side). The packaged app has `--self-check --window` in `build.yml`.
- **Result 2026-10-28:** green (headless Chromium, one-off Playwright script not kept in the repository; each list followed its action, 0 errors).

## P6. Connect an account, and send

- **Proves:** adding a Google or IMAP account, syncing it, removing it, and sending through the outbox.
- **Run:** in the app, *+ Add account* (Google OAuth in the browser, or IMAP with host, port and password). By hand this needs a real Google OAuth client or a real IMAP mailbox.
- **Expected:** the account appears in the rail, its mail is imported, *Disconnect* removes its secrets and local copy, a sent message is never sent twice.
- **Automated:** `tests/test_accounts_service.py` (`test_add_google_account_*`, `test_add_imap_account_ok`, `test_add_imap_account_bad_credentials`, `test_logout_account_deletes_secret_and_cache`), `tests/test_sync.py`, `tests/test_imap_sync.py`, `tests/test_outbox.py`, `tests/test_sender.py`, `tests/test_auth.py`, all on test doubles.
- **Result 2026-10-28:** green for the doubles (suite). Real connection and real send: not verifiable locally (needs a real provider account, forbidden for this check). In demo mode `POST /send` correctly answers 502 `sending is disabled in demo mode`, and `POST /accounts/1/sync` answers `{"changed":0}`.

## P7. The MCP server

- **Proves:** the nine tools are registered and answer with the documented shape.
- **Run:** `uv run pytest tests/test_mcp_server.py`. To use it for real, add it to an assistant as described in `docs/MCP.md`.
- **Expected:** `maily_list_accounts`, `maily_list_messages`, `maily_get_message`, `maily_search`, `maily_sync`, `maily_export_eml`, `maily_download_attachment`, `maily_trash`, `maily_send` are all registered.
- **Automated:** `tests/test_mcp_server.py` (`test_all_tools_registered`, `test_get_message_lists_real_attachments`).
- **Result 2026-10-28:** green (suite). A session with a real assistant over stdio: not verifiable locally here (needs an MCP client and real accounts).

## P8. Text check

- **Proves:** no em dash or en dash, no personal path or address in any tracked text file (CI job `check-text`).
- **Run:** `python3 scripts/check_text.py`
- **Expected:** `check-text ok (N files)`, exit 0.
- **Automated:** `.github/workflows/tests.yml` (job `check-text`), `tests/test_check_text.py` (`test_the_repository_itself_passes`).
- **Result 2026-10-28:** green (`check-text ok (125 files)`, before this page was added; run again with it).

## P9. Launcher self-check

- **Proves:** the launcher starts and the embedded pieces work (frontend, migrations, encryption, TLS bundle, local API libraries, window library).
- **Run:** `uv run python run_maily.py --version` then `uv run python run_maily.py --self-check`
- **Expected:** `Maily 0.9.1`, then seven `ok` lines and `Self-check passed.`, exit 0.
- **Automated:** `tests/test_selfcheck.py`, and `--self-check --window` on every built binary in `build.yml`.
- **Result 2026-10-28:** green (version 0.9.1, 7 checks ok, exit 0).

## P10. Build the downloadable apps

- **Proves:** PyInstaller builds the macOS, Windows and Linux apps, and each built binary passes its self-check.
- **Run:** `uv sync --group build` then the steps of `docs/BUILD.md`; or push a branch that touches the packaging (the paths listed in `.github/workflows/build.yml`), or run the Build workflow by hand (`workflow_dispatch`).
- **Expected:** `Maily.app` and the `.dmg`, the Windows zip, the Linux archive, with their `.sha256` files.
- **Automated:** `.github/workflows/build.yml` (on a pushed branch that touches the packaging, by hand, and from `release.yml`), `tests/test_release_workflow.py`.
- **Result 2026-10-28:** not verifiable locally: the `build` dependency group (PyInstaller) is not installed in this environment, and the three platforms are built on their own CI runners. The apps are unsigned, so no secret is needed in CI; the local build was simply not attempted.

## How to add a journey

1. Add a section `P<next number>` with the same six fields: what it proves, how to run it (exact command or steps, on demo or fictitious data only), expected result, automated or manual, result of the day.
2. Prefer an automated test: name it in the section, and keep manual steps only for what a test cannot do.
3. If it cannot be checked locally, write "not verifiable locally" and say why.
4. Update the date and the commit at the top each time the page is re-run. Use only `example.com`, `example.org` or `example.net` addresses, and run `python3 scripts/check_text.py`.
