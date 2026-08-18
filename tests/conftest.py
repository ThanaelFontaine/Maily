import pytest
from core import db as dbmod


@pytest.fixture
def database(tmp_path):
    d = dbmod.Database(tmp_path / "app.sqlite")
    yield d
    d.close()
