"""ImapClient.connect verifies the server certificate."""
import imaplib
import ssl

import pytest

from core.imap_client import ImapCertificateError, ImapClient, ImapError


class FakeSSL:
    seen = {}
    error = None

    def __init__(self, host, port, ssl_context=None):
        FakeSSL.seen = {"host": host, "port": port, "context": ssl_context}
        if FakeSSL.error:
            raise FakeSSL.error

    def login(self, user, password):
        return "OK", []


@pytest.fixture(autouse=True)
def fake_imaplib(monkeypatch):
    FakeSSL.error = None
    monkeypatch.setattr(imaplib, "IMAP4_SSL", FakeSSL)


def test_connect_requires_a_verified_certificate():
    ImapClient("imap.example.com", 993, "u", "p").connect()
    ctx = FakeSSL.seen["context"]
    assert ctx.verify_mode == ssl.CERT_REQUIRED and ctx.check_hostname is True


def test_untrusted_certificate_is_its_own_error():
    FakeSSL.error = ssl.SSLCertVerificationError("self-signed certificate")
    with pytest.raises(ImapCertificateError):
        ImapClient("imap.example.com", 993, "u", "p").connect()


def test_certificate_error_is_an_imap_error():
    assert issubclass(ImapCertificateError, ImapError)


def test_other_network_errors_stay_generic():
    FakeSSL.error = OSError("refused")
    with pytest.raises(ImapError) as e:
        ImapClient("imap.example.com", 993, "u", "p").connect()
    assert not isinstance(e.value, ImapCertificateError)
