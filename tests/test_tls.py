import ssl

from core import tls


def test_verified_context_checks_certificate_and_host():
    ctx = tls.verified_context()
    assert ctx.verify_mode == ssl.CERT_REQUIRED
    assert ctx.check_hostname is True
