# -*- mode: python ; coding: utf-8 -*-
"""Spec PyInstaller multiplateforme (macOS / Linux / Windows) pour Maily.

Build :  pyinstaller packaging/maily.spec --noconfirm
Sortie :  dist/Maily.app (macOS) ou dist/Maily/ (Linux/Windows).
"""
import os
import sys
from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))  # racine du repo
ICNS = os.path.join(ROOT, "packaging", "Maily.icns")
ICON = ICNS if os.path.exists(ICNS) else None

datas = [(os.path.join(ROOT, "frontend"), "frontend"),
         (os.path.join(ROOT, "migrations"), "migrations")]
binaries = []
# _cffi_backend : extension C requise par cryptography (Fernet) ; PyInstaller
# ne la detecte pas seul -> import cache explicite, sinon l'app crashe au
# demarrage (ModuleNotFoundError: No module named '_cffi_backend').
hiddenimports = ["app", "api", "core", "_cffi_backend"]

# Paquets a imports dynamiques (backends, protocoles) : on collecte tout.
# - cffi   : backend C de cryptography (Fernet).
# - anyio  : backend d'event-loop charge dynamiquement (anyio._backends._asyncio),
#            sinon FastAPI/Starlette plantent au 1er appel (No module named
#            'anyio._backends').
for pkg in ("uvicorn", "webview", "keyring", "googleapiclient",
            "google_auth_oauthlib", "google_auth_httplib2", "google.auth",
            "cryptography", "cffi", "anyio", "LocalAuthentication"):
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        pass
hiddenimports += collect_submodules("keyring.backends")

a = Analysis(
    [os.path.join(ROOT, "run_maily.py")],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "pytest", "_pytest", "mcp"],  # mcp : cote agent, pas dans l'app
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="Maily",
    debug=False,
    strip=False,
    upx=False,
    console=False,          # app fenetree (pas de console)
    icon=None,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="Maily")

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="Maily.app",
        icon=ICON,
        bundle_identifier="org.example.maily",
        info_plist={
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "12.0",
            "CFBundleShortVersionString": "0.4.0",
        },
    )
