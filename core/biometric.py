"""Touch ID unlock at launch (macOS, LocalAuthentication framework).

`require_unlock()` returns True if the user authenticates (fingerprint, with
the session password as a fallback), False if they cancel or fail. Security
policy:

- Outside macOS, if the framework is missing, or if no biometric sensor is set
  up: NO gate (returns True). The app is never locked on a machine without the
  hardware, so that the user is never locked out.
- On a Mac with Touch ID set up: authentication is REQUIRED; a failure or a
  cancellation returns False (the app must quit).
- Environment variable MAILY_NO_BIOMETRIC=1: disables the gate (debugging).

The call blocks and pumps the run loop of the main thread so that the system
sheet shows even before the application window starts.
"""
from __future__ import annotations
import os
import sys
import threading

# LAPolicyDeviceOwnerAuthentication = biometrics + session password fallback.
# (Avoids a lockout if the fingerprint fails several times.)
_LA_POLICY = 2


def _disabled() -> bool:
    return bool(os.environ.get("MAILY_NO_BIOMETRIC"))


def require_unlock(reason: str = "Unlock Maily") -> bool:
    if sys.platform != "darwin" or _disabled():
        return True
    try:
        import LocalAuthentication
        import Foundation
        import AppKit
    except Exception:
        # Framework unavailable: do not block.
        return True

    ctx = LocalAuthentication.LAContext.alloc().init()
    can, _err = ctx.canEvaluatePolicy_error_(_LA_POLICY, None)
    if not can:
        # No usable authentication mechanism: no gate.
        return True

    # Makes sure the process is an active GUI app, to show the Touch ID sheet.
    try:
        app = AppKit.NSApplication.sharedApplication()
        app.setActivationPolicy_(0)  # NSApplicationActivationPolicyRegular
        app.activateIgnoringOtherApps_(True)
    except Exception:
        pass

    result: dict = {}
    done = threading.Event()

    def _reply(success, error):
        result["ok"] = bool(success)
        done.set()

    ctx.evaluatePolicy_localizedReason_reply_(_LA_POLICY, reason, _reply)

    rl = Foundation.NSRunLoop.currentRunLoop()
    while not done.is_set():
        rl.runMode_beforeDate_(
            Foundation.NSDefaultRunLoopMode, Foundation.NSDate.dateWithTimeIntervalSinceNow_(0.05))
    return result.get("ok", False)
