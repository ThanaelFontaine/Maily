"""Le mode demonstration (scripts/demo.py) ne touche jamais les vraies donnees."""
import importlib.util
import pathlib
import pytest
from core.store import Store

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _demo():
    spec = importlib.util.spec_from_file_location("maily_demo", ROOT / "scripts" / "demo.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_seed_creates_fictitious_accounts_and_messages(database):
    demo = _demo()
    store = Store(database)
    demo.seed(store)
    emails = {a["email"] for a in store.list_accounts()}
    assert emails and all(e.endswith((".example.com", "@example.com", "@example.org", "@example.net")) for e in emails)
    assert store.list_messages(None, require_labels=["INBOX"], exclude_labels=[], trashed=False, limit=50, offset=0)


def test_refuses_the_real_data_dir(monkeypatch):
    demo = _demo()
    monkeypatch.delenv("MAILY_DATA_DIR", raising=False)
    real = str(demo._default_data_dir())
    with pytest.raises(SystemExit):
        demo.main(["--data-dir", real])
