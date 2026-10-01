#!/usr/bin/env bash
# macOS (Apple Silicon) build of Maily, then installation in /Applications,
# replacing the previous version. Usage: ./scripts/build_macos.sh
set -euo pipefail
cd "$(dirname "$0")/.."

echo "==> Build dependencies"
uv sync --group build >/dev/null

if [ ! -f packaging/Maily.icns ]; then
  echo "==> Generating the icon"
  uv run python packaging/make_icon.py
  ISET=packaging/Maily.iconset; rm -rf "$ISET"; mkdir -p "$ISET"
  for s in "16 16x16" "32 16x16@2x" "32 32x32" "64 32x32@2x" "128 128x128" \
           "256 128x128@2x" "256 256x256" "512 256x256@2x" "512 512x512" "1024 512x512@2x"; do
    # shellcheck disable=SC2086  # $s is split on purpose: "<pixels> <name>"
    set -- $s; sips -z "$1" "$1" packaging/maily.png --out "$ISET/icon_$2.png" >/dev/null
  done
  iconutil -c icns "$ISET" -o packaging/Maily.icns && rm -rf "$ISET"
fi

echo "==> PyInstaller"
uv run pyinstaller packaging/maily.spec --noconfirm >/dev/null
echo "    build: dist/Maily.app"

DEST="/Applications/Maily.app"
echo "==> Installing into $DEST (replaces the previous one)"
rm -rf "$DEST"
cp -R dist/Maily.app "$DEST"
xattr -dr com.apple.quarantine "$DEST" 2>/dev/null || true

# A single visible Maily: the build copy in the repository is removed,
# otherwise Spotlight/Launchpad shows two applications (dist/ + /Applications).
echo "==> Removing the build copy (dist/Maily.app)"
rm -rf dist/Maily.app

echo "==> Done: $DEST"
