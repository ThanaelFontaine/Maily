import logging
from core.logging_setup import RedactionFilter, configure_logging


def _apply(msg):
    f = RedactionFilter()
    rec = logging.LogRecord("maily", logging.INFO, __file__, 1, msg, None, None)
    f.filter(rec)
    return rec.getMessage()


def test_redacts_token_kv():
    assert "REDACTED" in _apply('refresh_token=1//0abcDEFghiJKL')
    assert "1//0abcDEFghiJKL" not in _apply('refresh_token=1//0abcDEFghiJKL')


def test_redacts_json_secret():
    out = _apply('{"client_secret": "GOCSPX-supersecretvalue12345"}')
    assert "GOCSPX-supersecretvalue12345" not in out


def test_keeps_normal_text():
    assert _apply("sync ok for account 3") == "sync ok for account 3"


def test_configure_writes_file(tmp_path):
    logger = configure_logging(tmp_path, level="INFO")
    logger.info("refresh_token=1//0secretTOKENvalue999")
    for h in logger.handlers:
        h.flush()
    content = (tmp_path / "maily.log").read_text()
    assert "1//0secretTOKENvalue999" not in content
    assert "REDACTED" in content
