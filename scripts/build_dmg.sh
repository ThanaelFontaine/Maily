#!/usr/bin/env bash
# Builds the macOS disk image of Maily from an already built Maily.app:
# a "Maily" volume showing Maily.app next to an Applications shortcut, on a
# background that says to drag one onto the other. Used by the CI
# (.github/workflows/build.yml) and usable as is on a Mac.
#
# Usage: scripts/build_dmg.sh [APP] [OUT_DIR]
#   APP      the bundle to package (default: dist/Maily.app)
#   OUT_DIR  where to write the image (default: dist)
# Writes OUT_DIR/Maily-X.Y.Z-macos-arm64.dmg and its .sha256 file.
# Installs nothing: the image is only written, never opened or copied to
# /Applications.
#
# Needs: macOS, uv, and the build group (`uv sync --group build`, which brings
# Pillow and dmgbuild). See docs/BUILD.md.
set -euo pipefail
cd "$(dirname "$0")/.."

APP="${1:-dist/Maily.app}"
OUT_DIR="${2:-dist}"

if [ "$(uname -s)" != "Darwin" ]; then
  echo "build_dmg.sh runs on macOS only (hdiutil)." >&2
  exit 1
fi
if [ ! -d "$APP/Contents/MacOS" ]; then
  echo "No application bundle at $APP: build it first (docs/BUILD.md)." >&2
  exit 1
fi

VERSION="$(uv run --no-sync python scripts/release_notes.py version)"
PLIST_VERSION="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$APP/Contents/Info.plist")"
if [ "$PLIST_VERSION" != "$VERSION" ]; then
  echo "$APP is version $PLIST_VERSION, the sources are $VERSION: rebuild it." >&2
  exit 1
fi

DMG="Maily-$VERSION-macos-arm64.dmg"
mkdir -p "$OUT_DIR"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/maily-dmg.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

echo "==> Background (1x and Retina 2x)"
uv run --no-sync python packaging/make_dmg_background.py "$WORK/bg" >/dev/null

echo "==> Disk image $DMG"
ICON_ARGS=()
if [ -f "$APP/Contents/Resources/Maily.icns" ]; then
  ICON_ARGS=(-D "icon=$APP/Contents/Resources/Maily.icns")
fi
rm -f "$OUT_DIR/$DMG" "$OUT_DIR/$DMG.sha256"
uv run --no-sync dmgbuild -s packaging/dmg_settings.py \
  -D "app=$APP" -D "background=$WORK/bg/background.png" ${ICON_ARGS[@]+"${ICON_ARGS[@]}"} \
  "Maily" "$OUT_DIR/$DMG"

echo "==> Checking the image"
hdiutil verify "$OUT_DIR/$DMG" >/dev/null
# Mounted read-only and without showing it in Finder, then detached.
MNT="$WORK/mnt"
mkdir -p "$MNT"
hdiutil attach "$OUT_DIR/$DMG" -readonly -nobrowse -noautoopen -mountpoint "$MNT" >/dev/null
STATUS=0
for f in "Maily.app/Contents/MacOS/Maily" ".background.tiff" ".DS_Store"; do
  [ -e "$MNT/$f" ] || { echo "Missing in the image: $f" >&2; STATUS=1; }
done
if [ "$(readlink "$MNT/Applications")" != "/Applications" ]; then
  echo "The Applications shortcut does not point to /Applications." >&2
  STATUS=1
fi
hdiutil detach "$MNT" -quiet || hdiutil detach "$MNT" -force -quiet
[ "$STATUS" -eq 0 ] || exit 1

(cd "$OUT_DIR" && shasum -a 256 "$DMG" > "$DMG.sha256" && cat "$DMG.sha256")
echo "==> Done: $OUT_DIR/$DMG"
