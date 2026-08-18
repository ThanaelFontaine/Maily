from core.config import Settings, load_settings


def test_defaults():
    s = Settings(_env_file=None)
    assert s.poll_interval_seconds == 180
    assert s.backfill_months == 12
    assert s.attachment_cache_mb == 500
    assert s.log_level == "INFO"


def test_env_override(monkeypatch):
    monkeypatch.setenv("MAILY_POLL_INTERVAL_SECONDS", "60")
    monkeypatch.setenv("MAILY_LOG_LEVEL", "DEBUG")
    s = load_settings()
    assert s.poll_interval_seconds == 60
    assert s.log_level == "DEBUG"
