# -*- mode: python ; coding: utf-8 -*-
"""Cross-platform PyInstaller spec (macOS / Linux / Windows) for Maily.

Build:   pyinstaller packaging/maily.spec --noconfirm
Output:  dist/Maily.app (macOS) or dist/Maily/ (Linux/Windows).
"""
import os
import re
import sys
from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))  # repository root
ICNS = os.path.join(ROOT, "packaging", "Maily.icns")
ICON = ICNS if os.path.exists(ICNS) else None

# Version read from core/__init__.py (kept equal to pyproject.toml).
with open(os.path.join(ROOT, "core", "__init__.py"), encoding="utf-8") as _f:
    VERSION = re.search(r'__version__ = "([^"]+)"', _f.read()).group(1)

datas = [(os.path.join(ROOT, "frontend"), "frontend"),
         (os.path.join(ROOT, "migrations"), "migrations")]
binaries = []
# _cffi_backend: C extension needed by cryptography (Fernet); PyInstaller does
# not detect it on its own, so it is an explicit hidden import, otherwise the
# app crashes at startup (ModuleNotFoundError: No module named '_cffi_backend').
hiddenimports = ["app", "api", "core", "_cffi_backend"]

# Packages with dynamic imports (backends, protocols): collect everything.
# - cffi   : C backend of cryptography (Fernet).
# - anyio  : event-loop backend loaded dynamically (anyio._backends._asyncio),
#            otherwise FastAPI/Starlette crash at the first call (No module
#            named 'anyio._backends').
# - certifi: the cacert.pem data file (TLS CA bundle) must be embedded,
#            otherwise requests (OAuth token exchange) crashes: "Could not find
#            a suitable TLS CA certificate bundle", certifi.where() points to
#            nothing.
for pkg in ("uvicorn", "webview", "keyring", "googleapiclient",
            "google_auth_oauthlib", "google_auth_httplib2", "google.auth",
            "cryptography", "cffi", "anyio", "certifi", "LocalAuthentication"):
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
    excludes=["tkinter", "pytest", "_pytest", "mcp"],  # mcp: agent side, not in the app
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
    console=False,          # windowed app (no console)
    icon=None,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="Maily")

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="Maily.app",
        icon=ICON,
        bundle_identifier="io.github.thanaelfontaine.maily",
        info_plist={
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "12.0",
            "CFBundleShortVersionString": VERSION,
            "CFBundleVersion": VERSION,
        },
    )
