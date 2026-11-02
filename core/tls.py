"""TLS context shared by every connection Maily opens itself (IMAP, update check)."""
from __future__ import annotations
import ssl


def verified_context() -> ssl.SSLContext:
    """Verifies the certificate and the host name (CERT_REQUIRED, check_hostname).

    The system's authorities, plus certifi's bundle when available: the
    packaged app embeds it (packaging/maily.spec), while the system's default
    paths may not exist inside a frozen bundle."""
    ctx = ssl.create_default_context()
    try:
        import certifi
        ctx.load_verify_locations(cafile=certifi.where())
    except (ImportError, OSError):
        pass
    return ctx
