"""Marks a file written from a mail as coming from the internet.

macOS: the quarantine properties of the file (what a browser sets on a
download), by the documented Foundation API; Launch Services then warns when
the user opens an app, a script or an executable. Windows: the Mark-of-the-Web,
an alternate data stream `Zone.Identifier` with the Internet zone. Elsewhere
there is no standard mark: nothing is written and no error is raised.

The mark is not a virus scan. A failure to set a mark the system supports
raises QuarantineFailed, which carries the kind of error and errno, never the
path or the file name (they come from a mail).
"""
from __future__ import annotations
import pathlib
import sys

APPLIED = "applied"
NOT_SUPPORTED = "not_supported"

AGENT_NAME = "Maily"

# Quarantine property keys and the "mail attachment" type. LSQuarantine.h
# declares them as external constants without their value, and the
# pyobjc LaunchServices binding is not installed, so they are read from the
# CoreServices bundle. Fallback: the values read there on 2026-11-15.
_BUNDLE_ID = "com.apple.CoreServices"
_MAC_NAMES = {
    "kLSQuarantineAgentNameKey": "LSQuarantineAgentName",
    "kLSQuarantineTypeKey": "LSQuarantineType",
    "kLSQuarantineTypeEmailAttachment": "LSQuarantineTypeEmailAttachment",
}

# GetVolumeInformationW flag of a volume that supports named streams
# (FILE_NAMED_STREAMS, 0x00040000), from the documentation of the function:
# https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-getvolumeinformationw
_FILE_NAMED_STREAMS = 0x00040000

_ZONE_TRANSFER = "[ZoneTransfer]\r\nZoneId=3\r\n"  # zone 3 = Internet


class QuarantineFailed(Exception):
    """The mark the system supports could not be set. Carries the kind of error
    and errno, never the path."""

    def __init__(self, kind: str, errno: int | None = None):
        super().__init__(kind)
        self.kind = kind
        self.errno = errno


def mac_names() -> dict[str, str]:
    """The three Launch Services strings, from the system bundle, with the
    literals as fallback."""
    names = dict(_MAC_NAMES)
    try:
        import Foundation
        import objc
        bundle = Foundation.NSBundle.bundleWithIdentifier_(_BUNDLE_ID)
        found: dict = {}
        objc.loadBundleVariables(bundle, found, [(k, b"@") for k in names])
        for k in names:
            if isinstance(found.get(k), str) and found[k]:
                names[k] = found[k]
    except Exception:
        pass
    return names


def _url_for(path: pathlib.Path):
    import Foundation
    return Foundation.NSURL.fileURLWithPath_(str(path))


def _mark_macos(path: pathlib.Path) -> str:
    try:
        import Foundation
        import objc
    except Exception as e:
        raise QuarantineFailed("foundation_unavailable") from e
    names = mac_names()
    try:
        # Called from the thread of uvicorn too: its own autorelease pool.
        with objc.autorelease_pool():
            props = {
                names["kLSQuarantineAgentNameKey"]: AGENT_NAME,
                names["kLSQuarantineTypeKey"]: names["kLSQuarantineTypeEmailAttachment"],
            }
            url = _url_for(path)
            # pyobjc returns (ok, error): the pair is always truthy, only ok counts.
            ok, _err = url.setResourceValue_forKey_error_(
                props, Foundation.NSURLQuarantinePropertiesKey, None)
    except Exception as e:
        raise QuarantineFailed("foundation_error") from e
    if not ok:
        raise QuarantineFailed("set_resource_value_failed")
    return APPLIED


def _windows_volume_has_streams(path: pathlib.Path) -> bool:
    """False only when the volume says it has no named streams (FAT32...).
    When the volume cannot be read, True: the stream write is tried."""
    try:
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        root = ctypes.create_unicode_buffer(260)
        if not k32.GetVolumePathNameW(str(path), root, 260):
            return True
        flags = wintypes.DWORD(0)
        if not k32.GetVolumeInformationW(root.value, None, 0, None, None,
                                         ctypes.byref(flags), None, 0):
            return True
        return bool(flags.value & _FILE_NAMED_STREAMS)
    except Exception:
        return True


def _mark_windows(path: pathlib.Path) -> str:
    if not _windows_volume_has_streams(path):
        return NOT_SUPPORTED
    try:
        with open(str(path) + ":Zone.Identifier", "w", encoding="ascii", newline="") as f:
            f.write(_ZONE_TRANSFER)
    except OSError as e:
        raise QuarantineFailed("zone_identifier_write_failed", e.errno) from e
    return APPLIED


def mark_from_mail(path: pathlib.Path, platform: str | None = None) -> str:
    """Marks path as coming from a mail. APPLIED or NOT_SUPPORTED; raises
    QuarantineFailed when the mark the system supports cannot be set."""
    platform = sys.platform if platform is None else platform
    if platform == "darwin":
        return _mark_macos(path)
    if platform == "win32":
        return _mark_windows(path)
    return NOT_SUPPORTED
