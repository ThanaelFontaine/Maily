from __future__ import annotations
import logging
import re
import pathlib
from logging.handlers import RotatingFileHandler

_SECRET_KEYS = r"(?:access_token|refresh_token|client_secret|authorization|token|password|api[_-]?key)"
_KV = re.compile(rf'(?i)({_SECRET_KEYS}\s*["\']?\s*[:=]\s*["\']?)([^\s"\',}}]+)')
_LONGB64 = re.compile(r'\b[A-Za-z0-9_\-]{40,}\b')
_REDACTED = "***REDACTED***"


class RedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        msg = _KV.sub(lambda m: m.group(1) + _REDACTED, msg)
        msg = _LONGB64.sub(_REDACTED, msg)
        record.msg = msg
        record.args = None
        return True


def configure_logging(logs_dir, level: str = "INFO") -> logging.Logger:
    logs_dir = pathlib.Path(logs_dir)
    logs_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("maily")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.handlers.clear()
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    redaction = RedactionFilter()
    fileh = RotatingFileHandler(logs_dir / "maily.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    streamh = logging.StreamHandler()
    for h in (fileh, streamh):
        h.setFormatter(fmt)
        h.addFilter(redaction)
        logger.addHandler(h)
    logger.propagate = False
    return logger
