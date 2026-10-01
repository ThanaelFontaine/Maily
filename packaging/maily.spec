# -*- mode: python ; coding: utf-8 -*-
"""Cross-platform PyInstaller spec (macOS / Linux / Windows) for Maily.

Build:   pyinstaller packaging/maily.spec --noconfirm
Output:  dist/Maily.app (macOS), dist/Maily/Maily.exe (Windows) or
         dist/Maily/maily (Linux).

On Linux the window uses the system's GTK 3 and WebKitGTK 4.1: the GTK,
GLib and WebKit libraries, their typelibs and their data are NOT embedded
(see LINUX_SYSTEM_PREFIXES below), because WebKitGTK starts helper processes
installed with the system library and they must match it.
"""
import os
import re
import sys
from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))  # repository root
ICNS = os.path.join(ROOT, "packaging", "Maily.icns")
ICON = ICNS if os.path.exists(ICNS) else None
PNG = os.path.join(ROOT, "packaging", "maily.png")
IS_LINUX = sys.platform.startswith("linux")
IS_WINDOWS = sys.platform == "win32"

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
if IS_LINUX:
    # PyGObject loads its Python overrides (gi.overrides.GLib, Gtk, ...) with
    # importlib at run time: without them GLib.idle_add has the raw C
    # signature and pywebview's GTK window never finishes loading.
    hiddenimports += collect_submodules("gi") + ["cairo"]

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

if IS_LINUX:
    # Everything that comes from the system (GTK, GLib, WebKitGTK, cairo,
    # libffi and their dependencies, GObject typelibs) is loaded from the
    # user's system at run time instead of being copied into the bundle. The
    # PyInstaller runtime hooks of GTK would point those libraries to the
    # bundle: they are left out too.
    LINUX_SYSTEM_PREFIXES = ("/usr/", "/lib/", "/lib64/")
    GI_RUNTIME_HOOKS = {"pyi_rth_gi", "pyi_rth_gtk", "pyi_rth_gdkpixbuf",
                        "pyi_rth_glib", "pyi_rth_gio"}
    GI_DATA_DIRS = ("gi_typelibs", "share", "lib/gdk-pixbuf", "etc")

    # Python itself stays embedded, even when it is a system Python in /usr.
    import sysconfig
    PYTHON_DIRS = tuple(os.path.abspath(sysconfig.get_paths()[k]) + os.sep
                        for k in ("stdlib", "platstdlib", "purelib", "platlib"))

    def _from_system(src):
        if not src:
            return False
        src = os.path.abspath(src)
        if src.startswith(PYTHON_DIRS) or os.path.basename(src).startswith("libpython"):
            return False
        return src.startswith(LINUX_SYSTEM_PREFIXES)

    def _gi_data(dest):
        dest = dest.replace(os.sep, "/")
        return any(dest == d or dest.startswith(d + "/") for d in GI_DATA_DIRS)

    a.binaries = [b for b in a.binaries if not _from_system(b[1])]
    a.datas = [d for d in a.datas if not (_from_system(d[1]) or _gi_data(d[0]))]
    a.scripts = [s for s in a.scripts if s[0] not in GI_RUNTIME_HOOKS]

pyz = PYZ(a.pure)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="maily" if IS_LINUX else "Maily",   # Linux: lower-case command name
    debug=False,
    strip=False,
    upx=False,
    console=False,          # windowed app (no console)
    icon=PNG if IS_WINDOWS else None,   # converted to .ico by Pillow
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
