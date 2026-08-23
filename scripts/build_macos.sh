#!/usr/bin/env bash
# Build macOS (Apple Silicon) de Maily, puis installation dans /Applications
# en remplaçant l'ancienne version. Usage : ./scripts/build_macos.sh
set -euo pipefail
cd "$(dirname "$0")/.."

echo "==> Dépendances de build"
uv sync --group build >/dev/null

if [ ! -f packaging/Maily.icns ]; then
  echo "==> (Ré)génération de l'icône"
  uv run python packaging/make_icon.py
  ISET=packaging/Maily.iconset; rm -rf "$ISET"; mkdir -p "$ISET"
  for s in "16 16x16" "32 16x16@2x" "32 32x32" "64 32x32@2x" "128 128x128" \
           "256 128x128@2x" "256 256x256" "512 256x256@2x" "512 512x512" "1024 512x512@2x"; do
    set -- $s; sips -z "$1" "$1" packaging/maily.png --out "$ISET/icon_$2.png" >/dev/null
  done
  iconutil -c icns "$ISET" -o packaging/Maily.icns && rm -rf "$ISET"
fi

echo "==> PyInstaller"
uv run pyinstaller packaging/maily.spec --noconfirm >/dev/null
echo "    build: dist/Maily.app"

DEST="/Applications/Maily.app"
echo "==> Installation dans $DEST (remplace l'ancienne)"
rm -rf "$DEST"
cp -R dist/Maily.app "$DEST"
xattr -dr com.apple.quarantine "$DEST" 2>/dev/null || true

# Une seule Maily visible : on supprime la copie de build dans le repo, sinon
# Spotlight/Launchpad affiche deux applications (dist/ + /Applications).
echo "==> Nettoyage de la copie de build (dist/Maily.app)"
rm -rf dist/Maily.app

echo "==> Terminé : $DEST"
