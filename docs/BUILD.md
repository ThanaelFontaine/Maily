# Building the downloadable apps

You do not need to build anything to use Maily: download the app for your system from the [latest release](https://github.com/ThanaelFontaine/Maily/releases/latest) (steps in the [README](../README.md#install)), or run it from source with `uv sync` then `uv run maily`. This page explains how each download is made, and how to make it yourself.

| Download | Built on | Content |
| --- | --- | --- |
| `Maily-X.Y.Z-macos-arm64.dmg` | macOS, Apple Silicon | Disk image: `Maily.app` next to an *Applications* shortcut |
| `Maily-X.Y.Z-windows-x64.zip` | Windows, x64 | Folder `Maily\` with `Maily.exe` and its `_internal\` folder |
| `Maily-X.Y.Z-linux-x64.tar.gz` | Ubuntu 24.04, x64 | Folder `Maily/` with the `maily` binary, `_internal/`, `maily.desktop`, `maily.png` and `INSTALL.txt` |

Each file has a `Maily-X.Y.Z-....sha256` next to it (`<hash>  <file name>`, the format of `shasum -a 256 -c` and `sha256sum -c`). None of the apps is signed: see the README for the first launch on [macOS](../README.md#macos-apple-silicon), [Windows](../README.md#windows-x64) and [Linux](../README.md#linux-x64).

## How the app is packaged

Maily is packaged with **PyInstaller** (spec: [`packaging/maily.spec`](../packaging/maily.spec), entry point: [`run_maily.py`](../run_maily.py)) in "one folder" mode. The `frontend/` and `migrations/` folders are embedded; paths are "frozen-aware" (`sys._MEIPASS`). The version comes from `core/__init__.py`, kept equal to `pyproject.toml` by a test.

> **No cross-compilation.** Each platform builds on itself: a macOS app on a Mac, a Windows app on Windows, a Linux app on Linux.

A built app uses the same data folder as the source version (see [Where your data lives](../README.md#where-your-data-lives)), so both share accounts and mail. The MCP server is not part of the packaged app: it always runs from a source folder (see [docs/MCP.md](MCP.md)).

### What differs between systems

| | macOS | Windows | Linux |
| --- | --- | --- | --- |
| Data folder | `~/Library/Application Support/Maily` | `%APPDATA%\Maily` | `~/.local/share/maily` (or `$XDG_DATA_HOME/maily`) |
| Window (pywebview) | WebKit (built in) | Edge WebView2 Runtime | GTK 3 and WebKitGTK 4.1 from the system |
| Secrets | encrypted file, `0600` | encrypted file, in the user's profile | encrypted file, `0600` |
| Unlock at launch | Touch ID, when set up | none | none |
| Frosted glass | native blur | opaque fallback | transparent window, blur left to the compositor |

The secrets are always in the encrypted file `secrets.enc` (see [SECURITY.md](../SECURITY.md)). At launch, Maily also imports, once, the entries an older version left in the system keyring (the macOS Keychain, the Windows Credential Locker, the freedesktop Secret Service on Linux, through [keyring](https://pypi.org/project/keyring/)); when there is nothing to import, or no keyring at all, it simply moves on.

### Checking a built app

Every built binary has two command-line checks, which the CI runs before packaging:

```bash
Maily --version                  # prints "Maily X.Y.Z"
Maily --self-check               # embedded frontend, migrations, encryption, TLS bundle, local API, window library
Maily --self-check --window      # the same, then opens a real window on the local API and checks that the page loads
Maily --self-check --report FILE # also writes the result to FILE
```

`Maily` stands for `dist/Maily.app/Contents/MacOS/Maily`, `dist\Maily\Maily.exe` or `dist/Maily/maily`. The self-check uses a throwaway database in a temporary folder: no account, no network, and the real data folder is never touched. It exits with status 0 when everything passed. `Maily.exe` is a windowed program without console output: use `--report` there. `--tls-selftest` also checks a real TLS connection to Google (network needed).

## Common prerequisite

```bash
uv sync --group build      # dependencies + PyInstaller + Pillow (+ dmgbuild on macOS)
```

## macOS: the disk image

```bash
uv run pyinstaller packaging/maily.spec --noconfirm     # -> dist/Maily.app
scripts/build_dmg.sh dist/Maily.app dist                # -> dist/Maily-X.Y.Z-macos-arm64.dmg (+ .sha256)
```

[`scripts/build_dmg.sh`](../scripts/build_dmg.sh) installs nothing; it only writes the image:

1. it checks that the bundle's version is the version of the sources;
2. it draws the background, at 1x and Retina 2x, with [`packaging/make_dmg_background.py`](../packaging/make_dmg_background.py) (Pillow): an arrow from Maily to *Applications*, "Drag Maily to Applications" and a line about the first launch;
3. it builds a compressed (`UDZO`) image named **Maily** with [dmgbuild](https://github.com/dmgbuild/dmgbuild) (MIT license) and the settings in [`packaging/dmg_settings.py`](../packaging/dmg_settings.py): `Maily.app` at the left, a symbolic link to `/Applications` at the right, 128 point icons, a 640 x 400 point window without toolbar or sidebar, the Maily icon as volume icon. dmgbuild writes the Finder layout (`.DS_Store`) itself, so it works without a Finder session, on a CI runner too ([dmgbuild settings](https://dmgbuild.readthedocs.io/en/latest/settings.html)); it combines `background.png` and `background@2x.png` into one HiDPI TIFF with macOS's `tiffutil`;
4. it checks the image (`hdiutil verify`), mounts it read-only without showing it in Finder to check that `Maily.app`, the background and the *Applications* link are there, unmounts it, and writes the `.sha256` file.

The helper script `scripts/build_macos.sh` is for a developer's own Mac: it builds the app and **replaces `/Applications/Maily.app`** with it (then removes `dist/Maily.app` so that Spotlight shows a single Maily). Read it before running it.

The app is **neither signed nor notarized**. For wide distribution, sign it with an Apple Developer ID certificate and notarize it (`codesign`, `notarytool`). Until then, the first launch needs one approval ([Apple's steps](https://support.apple.com/guide/mac-help/open-a-mac-app-from-an-unknown-developer-mh40616/mac)): try to open Maily once, then *System Settings > Privacy & Security > Open Anyway*. Since macOS 15 Sequoia, Control-click > *Open* no longer bypasses this check ([Apple developer news](https://developer.apple.com/news/?id=saqachfa)). From a terminal, you can instead remove the quarantine flag that macOS puts on downloaded files: `xattr -dr com.apple.quarantine /Applications/Maily.app`. Only do this for a file whose checksum you checked.

Touch ID works in the packaged app (framework `LocalAuthentication`, embedded).

## Windows (x64)

pywebview draws the window with the **Microsoft Edge WebView2 Runtime**, through pythonnet ([pywebview installation](https://pywebview.flowrl.com/guide/installation.html)). Microsoft includes the runtime in Windows 11, and the vast majority of Windows 10 devices already have it ([WebView2 distribution](https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/distribution)).

```powershell
uv sync --group build
uv run pyinstaller packaging/maily.spec --noconfirm
# -> dist\Maily\Maily.exe   (icon converted from packaging\maily.png by Pillow)
Start-Process dist\Maily\Maily.exe -ArgumentList '--self-check','--window','--report','check.txt' -Wait; Get-Content check.txt
```

The CI zips the `dist\Maily` folder with 7-Zip (`7z a -tzip`), so that the archive holds a `Maily` folder; `Compress-Archive -Path dist\Maily -DestinationPath Maily-X.Y.Z-windows-x64.zip` gives the same layout. `Maily.exe` is not signed: Microsoft Defender SmartScreen may show *Windows protected your PC*, with *More info* then *Run anyway* to start it ([SmartScreen reputation](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/smartscreen-reputation)).

The test suite is not run on Windows by the CI (several tests check POSIX permissions); the built app is checked with `--self-check --window`.

## Linux (x64)

The window uses the system's **GTK 3 and WebKitGTK 4.1** through PyGObject. The spec does **not** embed the GTK, GLib, WebKit and cairo libraries, their typelibs and their data, nor the PyInstaller runtime hooks that would point GTK to the bundle: WebKitGTK starts helper processes that are installed with the system library and must match it. The archive therefore needs the system packages below, and a glibc at least as recent as the build machine's (2.39, Ubuntu 24.04). Python, PyGObject and every other dependency are embedded.

**To build**, install the build tools of PyGObject ([PyGObject getting started](https://pygobject.gnome.org/getting_started.html)) and the window libraries, then the `linux-gui` dependency group (PyGObject is compiled from source):

```bash
# Debian 13, Ubuntu 24.04 or newer
sudo apt install gcc pkg-config libgirepository-2.0-dev libcairo2-dev gir1.2-gtk-3.0 gir1.2-webkit2-4.1
# Fedora: sudo dnf install gcc pkg-config gobject-introspection-devel cairo-gobject-devel webkit2gtk4.1 gtk3
uv sync --group build --group linux-gui
uv run pyinstaller packaging/maily.spec --noconfirm
# -> dist/Maily/maily
dist/Maily/maily --self-check --window
cp packaging/linux/maily.desktop packaging/linux/INSTALL.txt dist/Maily/   # plus maily.png, 512 x 512
tar -C dist -czf Maily-X.Y.Z-linux-x64.tar.gz Maily
```

**To run the archive**, only the runtime packages are needed (they are also in [`packaging/linux/INSTALL.txt`](../packaging/linux/INSTALL.txt)):

| Distribution | Packages |
| --- | --- |
| Debian 13, Ubuntu 24.04 or newer | `gir1.2-webkit2-4.1 libgirepository-2.0-0 libcairo-gobject2` |
| Fedora 40 or newer | `webkit2gtk4.1 gtk3 cairo-gobject gobject-introspection` |
| Arch Linux | `webkit2gtk-4.1 gtk3 gobject-introspection-runtime` |

The CI runs the archive on Ubuntu 24.04, Debian 13 and Fedora with exactly these packages; the Arch Linux list comes from the Arch package database and is not checked by the CI. `gobject-introspection` (Fedora) and `gobject-introspection-runtime` (Arch) bring the `cairo` typelib that PyGObject needs; Debian's `gir1.2-webkit2-4.1` already pulls it in.

**To run from source** on Linux, install the build packages above, then `uv sync --group linux-gui` and `uv run maily`. Without GTK, you can install `pyside6` and run with `PYWEBVIEW_GUI=qt` (not tested by the CI). On KDE, pywebview tries Qt first, then GTK.

The archive's `maily.desktop` runs `maily` from the `PATH` with the `maily` icon; `INSTALL.txt` shows how to link the binary into `~/.local/bin` and copy the entry and the icon into `~/.local/share`.

## Releases

Releases are created by the CI, not by hand (see [CONTRIBUTING.md](../CONTRIBUTING.md#releasing-a-version)). After the tests pass on a push to `main`, [`.github/workflows/release.yml`](../.github/workflows/release.yml) runs three jobs, and a release is never visible without all its downloads:

1. **plan** reads the version in `pyproject.toml` (`scripts/release_notes.py version`) and its section of `CHANGELOG.md` (`scripts/release_notes.py notes X.Y.Z`, which fails if the section is missing or empty). If release `vX.Y.Z` is already published with all its files (`scripts/release_notes.py assets X.Y.Z` lists the six of them), the other jobs are skipped.
2. **build** calls [`.github/workflows/build.yml`](../.github/workflows/build.yml) on the tested commit. Its jobs publish nothing; each keeps its files as a workflow artifact:
   - **macOS** (`macos-latest`, Apple Silicon): `uv sync --locked --group build`, PyInstaller, then checks that the bundle version is `X.Y.Z`, that the `Maily` executable is `arm64` (`lipo -archs`) and that every embedded binary has an `arm64` slice, runs `Maily --version` and `Maily --self-check --window`, and finally `scripts/build_dmg.sh`.
   - **Windows** (`windows-latest`): PyInstaller, `Maily.exe --self-check --window --report` (the version is checked in the report), then the zip and its checksum.
   - **Linux** (`ubuntu-latest`): the system packages, `uv sync --locked --group build --group linux-gui`, PyInstaller, a check that no GTK, GLib or WebKit library nor typelib was embedded, `maily --version` and `maily --self-check --window` under `xvfb-run`, then the archive and its checksum.
   - **Linux archive on clean systems**: the archive is extracted and run (`--self-check --window`, with Xvfb) in `debian:trixie` and `fedora:latest` containers that only have the runtime packages listed above. In the CI only, the WebKit sandbox is turned off (`WEBKIT_DISABLE_SANDBOX_THIS_IS_DANGEROUS=1`), because CI machines and containers restrict the user namespaces it needs, and so is the DMA-BUF renderer (`WEBKIT_DISABLE_DMABUF_RENDERER=1`), which a virtual display does not support.
3. **publish** runs only after every build succeeded: it checks that the six files are there and that each build matches its checksum, creates the tag `vX.Y.Z` on the tested commit, creates a **draft** release with the notes and all the files, then publishes it (`gh release edit vX.Y.Z --draft=false`). Last, it announces the new release in the "prod maily" channel of Discord: title, link and the first lines of the notes, with no mention and no link preview, through the webhook kept in the `DISCORD_RELEASES_WEBHOOK_URL` repository secret. This step runs only when the release was just published, does nothing if the secret is not set, and never fails the release (a Discord error only leaves a warning).

Running the workflow again after a failure resumes: a tag already on the same commit is reused, an unpublished draft left by an interrupted run is replaced, and a release published earlier without some files only gets the missing ones. The chain starts from one workflow because a tag or a release created with the workflow's `GITHUB_TOKEN` does not start other workflows.

`build.yml` also runs on a push to any branch other than `main` that touches the packaging (the spec, `packaging/`, `scripts/build_dmg.sh`, `run_maily.py`, `app/selfcheck.py`, `pyproject.toml`, `uv.lock` or the workflow itself), and by hand (*Actions > Build > Run workflow*), so that a packaging change is checked on the three systems before it reaches `main`.
