#!/bin/sh
# Maily installer for macOS (Apple Silicon) and Linux (x64).
#
#   curl -fsSL https://github.com/ThanaelFontaine/Maily/releases/latest/download/install.sh | sh
#
# This file is attached to every release (from 0.10.0) and lives in the repository
# at packaging/install/install.sh. It downloads the latest release from GitHub
# (https://github.com/ThanaelFontaine/Maily/releases), checks it against its published
# SHA-256, checks its build provenance attestation with the GitHub CLI (gh) when
# it can, then installs it:
#   macOS  Maily.app in /Applications (or ~/Applications when /Applications is not writable)
#   Linux  ~/.local/opt/Maily, the `maily` command in ~/.local/bin and an entry in the app menu
# Running it again updates Maily. Your accounts and mail live in the data folder and are kept.
# Nothing here needs sudo.
#
# Options (environment variables): MAILY_VERSION=0.9.2 installs that version,
# MAILY_INSTALL_DIR=/path installs somewhere else, MAILY_REQUIRE_ATTESTATION=1
# refuses to install a download whose attestation could not be checked.

set -eu

REPO="ThanaelFontaine/Maily"
SITE="https://maily.thanaelfontaine.eu"
# The workflow that builds and attests every release.
SIGNER="$REPO/.github/workflows/release.yml"
# The first release with attestations.
ATTESTED_FROM="0.10.0"

say() { printf '%s\n' "$*"; }
fail() { printf 'Maily: %s\n' "$*" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || fail "this installer needs $1."; }
# version_ge A B: success when version A is B or newer (dotted numbers).
version_ge() {
  awk -v a="$1" -v b="$2" 'BEGIN {
    n = split(a, x, "."); m = split(b, y, "."); k = (n > m ? n : m)
    for (i = 1; i <= k; i++) { p = x[i] + 0; q = y[i] + 0; if (p > q) exit 0; if (p < q) exit 1 }
    exit 0 }'
}

need curl
need tar
need uname

# The system and the build that fits it.
os="$(uname -s)"
arch="$(uname -m)"
case "$os" in
  Darwin)
    system="macOS"
    # A terminal running under Rosetta reports x86_64: ask the hardware.
    if [ "$arch" != "arm64" ] && [ "$(sysctl -n hw.optional.arm64 2>/dev/null || echo 0)" != "1" ]; then
      fail "the ready-made app needs a Mac with Apple Silicon. On an Intel Mac, run Maily from source: https://github.com/$REPO#option-b-run-from-source"
    fi
    build="macos-arm64.dmg"
    need hdiutil
    need ditto
    ;;
  Linux)
    case "$arch" in
      x86_64|amd64) build="linux-x64.tar.gz"; system="Linux" ;;
      *) fail "no ready-made app for Linux $arch yet. Run Maily from source: https://github.com/$REPO#option-b-run-from-source" ;;
    esac
    ;;
  *)
    fail "this installer is for macOS and Linux. On Windows, in PowerShell: irm https://github.com/$REPO/releases/latest/download/install.ps1 | iex"
    ;;
esac

# The version: the one asked for, or the latest release (GitHub redirects
# /releases/latest to /releases/tag/vX.Y.Z).
version="${MAILY_VERSION:-}"
if [ -z "$version" ]; then
  latest="$(curl -fsSLI -o /dev/null -w '%{url_effective}' "https://github.com/$REPO/releases/latest")" \
    || fail "could not reach GitHub. Check your connection and try again."
  version="${latest##*/tag/v}"
fi
version="${version#v}"
case "$version" in
  *[!0-9.]*|"") fail "could not find the latest version (got: $version)." ;;
esac

file="Maily-$version-$build"
url="https://github.com/$REPO/releases/download/v$version/$file"

tmp="$(mktemp -d 2>/dev/null || mktemp -d -t maily)"
mnt=""
cleanup() {
  if [ -n "$mnt" ]; then hdiutil detach -quiet "$mnt" >/dev/null 2>&1 || true; fi
  rm -rf "$tmp"
}
trap cleanup EXIT
trap 'exit 130' INT TERM

say "Downloading Maily $version for $system..."
curl -fL --progress-bar -o "$tmp/$file" "$url" || fail "download failed: $url"
curl -fsSL -o "$tmp/$file.sha256" "$url.sha256" || fail "checksum download failed: $url.sha256"

# The .sha256 file reads "<hash>  <name>".
expected="$(cut -d ' ' -f 1 < "$tmp/$file.sha256" | tr 'A-F' 'a-f')"
if command -v sha256sum >/dev/null 2>&1; then
  actual="$(sha256sum "$tmp/$file" | cut -d ' ' -f 1)"
else
  actual="$(shasum -a 256 "$tmp/$file" | cut -d ' ' -f 1)"
fi
[ -n "$expected" ] && [ "$expected" = "$actual" ] || fail "the download does not match its SHA-256 checksum. Nothing was installed."
say "Checksum verified."

# Provenance. The checksum above only proves that the download matches the file
# published next to it, which comes from the same place. The attestation proves
# that the file was built from this repository by its release workflow: the
# GitHub CLI checks it against GitHub's records (a sign-in with `gh auth login`
# is needed, https://cli.github.com/manual/gh_attestation_verify).
# Without it we say so and go on, unless MAILY_REQUIRE_ATTESTATION=1.
unverified() {
  say "Warning: could not check where this download was built ($*)."
  if [ "${MAILY_REQUIRE_ATTESTATION:-}" = "1" ]; then
    fail "MAILY_REQUIRE_ATTESTATION=1: nothing was installed."
  fi
  say "Continuing with the checksum only. Details: https://github.com/$REPO/blob/main/SECURITY.md#verify-a-download"
}
if ! version_ge "$version" "$ATTESTED_FROM"; then
  unverified "Maily $version is older than $ATTESTED_FROM, the first release with attestations"
elif ! command -v gh >/dev/null 2>&1; then
  unverified "the GitHub CLI (gh) is not installed: https://cli.github.com"
elif ! gh attestation verify --help >/dev/null 2>&1; then
  unverified "this version of gh has no \`gh attestation verify\`: update it"
elif ! gh auth status >/dev/null 2>&1; then
  unverified "gh is not signed in: run \`gh auth login\`"
else
  say "Checking the build attestation with gh..."
  gh attestation verify "$tmp/$file" --repo "$REPO" --signer-workflow "$SIGNER" \
    || fail "the attestation of this download could not be verified. Nothing was installed."
  say "Attestation verified: built by $SIGNER."
fi

if [ "$os" = "Darwin" ]; then
  pgrep -xq Maily 2>/dev/null && fail "Maily is open. Quit it, then run this command again."
  dest="${MAILY_INSTALL_DIR:-/Applications}"
  if [ -z "${MAILY_INSTALL_DIR:-}" ] && [ ! -w "$dest" ]; then
    dest="$HOME/Applications"
  fi
  mkdir -p "$dest"
  mnt="$tmp/mnt"
  mkdir -p "$mnt"
  hdiutil attach -nobrowse -readonly -quiet -mountpoint "$mnt" "$tmp/$file" || { mnt=""; fail "could not open the disk image."; }
  [ -d "$mnt/Maily.app" ] || fail "Maily.app is missing from the disk image."
  rm -rf "$dest/Maily.app.new"
  ditto "$mnt/Maily.app" "$dest/Maily.app.new"
  rm -rf "$dest/Maily.app"
  mv "$dest/Maily.app.new" "$dest/Maily.app"
  say ""
  say "Maily $version is installed in $dest/Maily.app."
  say "Open it from $dest, or with: open \"$dest/Maily.app\""
else
  pgrep -x maily >/dev/null 2>&1 && fail "Maily is open. Quit it, then run this command again."
  base="${MAILY_INSTALL_DIR:-$HOME/.local/opt}"
  mkdir -p "$base" "$tmp/x"
  tar -xzf "$tmp/$file" -C "$tmp/x"
  [ -x "$tmp/x/Maily/maily" ] || fail "the archive does not hold Maily/maily."
  rm -rf "$base/Maily.new"
  mv "$tmp/x/Maily" "$base/Maily.new"
  rm -rf "$base/Maily"
  mv "$base/Maily.new" "$base/Maily"
  app="$base/Maily"

  # The command and the app menu entry (freedesktop locations in the home folder).
  bin="$HOME/.local/bin"
  share="${XDG_DATA_HOME:-$HOME/.local/share}"
  mkdir -p "$bin" "$share/applications" "$share/icons/hicolor/512x512/apps"
  ln -sf "$app/maily" "$bin/maily"
  cp "$app/maily.png" "$share/icons/hicolor/512x512/apps/maily.png"
  sed "s|^Exec=.*|Exec=\"$app/maily\"|" "$app/maily.desktop" > "$share/applications/maily.desktop"

  say ""
  say "Maily $version is installed in $app."
  say "Open it from your applications menu, or run: $bin/maily"
  case ":$PATH:" in
    *":$bin:"*) ;;
    *) say "($bin is not in your PATH: add it to type just \"maily\".)" ;;
  esac

  # The window needs WebKitGTK 4.1. Only a hint: installing system packages is up to you.
  if command -v ldconfig >/dev/null 2>&1 && ! ldconfig -p 2>/dev/null | grep -q 'libwebkit2gtk-4.1'; then
    say ""
    say "Maily's window needs GTK 3 and WebKitGTK 4.1, which seem to be missing. For example:"
    say "  Debian 13, Ubuntu 24.04 or newer: sudo apt install gir1.2-webkit2-4.1 libgirepository-2.0-0 libcairo-gobject2"
    say "  Fedora 40 or newer:              sudo dnf install webkit2gtk4.1 gtk3 cairo-gobject gobject-introspection"
    say "  Arch Linux:                      sudo pacman -S webkit2gtk-4.1 gtk3 gobject-introspection-runtime"
  fi
fi

say ""
say "To update Maily later, run the same command again. Maily also tells you when a new version is out."
say "Next: connect your mailboxes and your AIs, $SITE/#start"
