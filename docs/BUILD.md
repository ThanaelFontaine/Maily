# Building a standalone application

You do not need to build anything to use Maily: `uv run python -m app.bootstrap` runs it from the source folder. This page is for people who want a double-clickable application (`Maily.app` on macOS, an executable folder on Linux and Windows).

Maily is packaged with **PyInstaller** (spec: [`packaging/maily.spec`](../packaging/maily.spec), entry point: [`run_maily.py`](../run_maily.py)). The `frontend/` and `migrations/` folders are embedded; paths are "frozen-aware" (`sys._MEIPASS`). The version shown in the app bundle is read from `core/__init__.py`.

> **No cross-compilation.** Each platform builds on itself: a macOS binary on a Mac, a Windows binary on Windows, a Linux binary on Linux.

The packaged app uses the same data folder as the source version (see the README), so both share accounts and mail.

## Common prerequisite

```bash
uv sync --group build      # dependencies + PyInstaller + Pillow
```

## macOS (Apple Silicon)

```bash
uv run pyinstaller packaging/maily.spec --noconfirm
# -> dist/Maily.app
open dist/Maily.app
```

The helper script `scripts/build_macos.sh` does the same, regenerates the icon if needed, and **replaces `/Applications/Maily.app`** with the new build (then removes `dist/Maily.app` so that Spotlight shows a single Maily). Read it before running it.

To share the bundle:

```bash
cd dist && zip -r ../Maily-macos-arm64.zip Maily.app
```

The bundle is **neither signed nor notarized**. On first launch, right-click, *Open*, or remove the quarantine flag: `xattr -dr com.apple.quarantine dist/Maily.app`. For wide distribution, sign it with an Apple Developer certificate and notarize it (`codesign`, `notarytool`).

Touch ID works in the packaged app (framework `LocalAuthentication`, embedded).

## Linux (x86_64)

pywebview needs **GTK and WebKit2GTK** (Debian/Ubuntu package names):

```bash
sudo apt-get update
sudo apt-get install -y \
  libgtk-3-0 gir1.2-gtk-3.0 gir1.2-webkit2-4.1 libwebkit2gtk-4.1-0 \
  libgirepository1.0-dev libcairo2-dev pkg-config python3-dev
uv sync --group build
uv pip install pygobject          # GTK bindings
uv run pyinstaller packaging/maily.spec --noconfirm
# -> dist/Maily/   (run: ./dist/Maily/Maily)
cd dist && tar czf ../Maily-linux-x64.tar.gz Maily
```

Recent Ubuntu releases may need a specific PyGObject version matching their `girepository`; if `pygobject` fails to build, try `uv pip install "pygobject==3.50.0"`. Without GTK, you can install `pyside6` and run with `PYWEBVIEW_GUI=qt`.

The same system packages are needed to run from source on Linux (`uv pip install pygobject`, then `uv run python -m app.bootstrap`).

## Windows (x86_64)

pywebview uses **WebView2 (Edge Chromium)**, present on up-to-date Windows 10 and 11.

```powershell
uv sync --group build
uv run pyinstaller packaging/maily.spec --noconfirm
# -> dist\Maily\   (run: dist\Maily\Maily.exe)
Compress-Archive -Path dist\Maily -DestinationPath Maily-windows-x64.zip
```

## Checking TLS in a built app

The packaged binary embeds the `certifi` CA bundle. To check it:

```bash
dist/Maily.app/Contents/MacOS/Maily --tls-selftest     # macOS
./dist/Maily/Maily --tls-selftest                      # Linux
```

It should print `TLS OK`.

## Releases

Releases are created by the CI, not by hand: after the tests pass on a push to `main`, `.github/workflows/release.yml` reads the version in `pyproject.toml`, and if the tag `vX.Y.Z` does not exist yet, creates it with a GitHub release whose notes are the matching section of `CHANGELOG.md`. See [CONTRIBUTING.md](../CONTRIBUTING.md#releasing-a-version).

Binaries built on each platform can then be attached to that release:

```bash
gh release upload vX.Y.Z Maily-macos-arm64.zip     # from a Mac
gh release upload vX.Y.Z Maily-linux-x64.tar.gz    # from Linux
gh release upload vX.Y.Z Maily-windows-x64.zip     # from Windows
```
