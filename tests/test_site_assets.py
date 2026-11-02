"""scripts/site_assets.py: the demo command line carries the token it generates."""
import importlib.util
import pathlib
from unittest import mock

import pytest

pytest.importorskip("PIL")

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _site_assets():
    spec = importlib.util.spec_from_file_location("site_assets", ROOT / "scripts" / "site_assets.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_demo_starts_with_its_token_on_the_command_line():
    mod = _site_assets()
    seen = {}

    def fake_popen(cmd, **_kwargs):
        seen["cmd"] = cmd
        return mock.Mock()

    demo = mod.Demo("fr")
    with mock.patch.object(mod.subprocess, "Popen", fake_popen), \
            mock.patch.object(mod.urllib.request, "urlopen", return_value=None), \
            mock.patch.object(mod.tempfile, "mkdtemp", return_value="/tmp/x"):
        demo.__enter__()
    cmd = seen["cmd"]
    assert cmd[cmd.index("--token") + 1] == demo.token
    assert cmd[cmd.index("--lang") + 1] == "fr"
    assert demo.url.endswith("#k=" + demo.token)
