# Générer les exécutables (macOS / Linux / Windows)

Maily est empaqueté avec **PyInstaller** (spec : [`packaging/maily.spec`](../packaging/maily.spec)).
Le `frontend/` et les `migrations/` sont embarqués dans le binaire ; les chemins sont
« frozen-aware » (`sys._MEIPASS`). Point d'entrée : [`run_maily.py`](../run_maily.py).

> ⚠️ **Pas de cross-compilation.** Chaque plateforme se construit **sur elle-même**
> (un binaire macOS se construit sur un Mac, etc.). La CI GitHub Actions
> ([`.github/workflows/release.yml`](../.github/workflows/release.yml)) le fait
> automatiquement pour Linux et Windows à chaque tag `v*` ; le binaire **macOS ARM**
> est fourni depuis un Mac Apple Silicon.

## Prérequis communs

```bash
uv sync --group build      # installe les deps + PyInstaller
```

## macOS (Apple Silicon / arm64)

```bash
uv run pyinstaller packaging/maily.spec --noconfirm
# -> dist/Maily.app
```

Lancer : `open dist/Maily.app`. Pour distribuer, zipper le bundle :

```bash
cd dist && zip -r ../Maily-macos-arm64.zip Maily.app
```

> Le bundle n'est **pas signé/notarié**. Au premier lancement : clic droit → « Ouvrir »,
> ou `xattr -dr com.apple.quarantine dist/Maily.app`. Pour une distribution large,
> signer avec un certificat Apple Developer puis notariser (`codesign` + `notarytool`).

## Linux (x86_64)

pywebview a besoin de **GTK + WebKit2GTK** :

```bash
sudo apt-get update
sudo apt-get install -y \
  libgtk-3-0 gir1.2-gtk-3.0 gir1.2-webkit2-4.1 libwebkit2gtk-4.1-0 \
  libgirepository1.0-dev libcairo2-dev pkg-config python3-dev
uv sync --group build
uv pip install pygobject          # binding GTK
uv run pyinstaller packaging/maily.spec --noconfirm
# -> dist/Maily/  (lancer : ./dist/Maily/Maily)
cd dist && tar czf ../Maily-linux-x64.tar.gz Maily
```

> Alternative sans GTK : installer `pyside6` et lancer avec `PYWEBVIEW_GUI=qt`.

## Windows (x86_64)

pywebview utilise **WebView2 (Edge Chromium)**, présent sur Windows 10/11 à jour.

```powershell
uv sync --group build
uv run pyinstaller packaging/maily.spec --noconfirm
# -> dist\Maily\  (lancer : dist\Maily\Maily.exe)
Compress-Archive -Path dist\Maily -DestinationPath Maily-windows-x64.zip
```

## Publication d'une release

Pousser un tag `vX.Y.Z` déclenche la CI qui construit Linux + Windows et les attache à
la release GitHub :

```bash
git tag v0.1.0 && git push origin v0.1.0
```

Le binaire macOS ARM est construit localement et ajouté à la même release :

```bash
gh release upload v0.1.0 Maily-macos-arm64.zip --clobber
```
