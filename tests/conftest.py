import os
import pytest
from kycli.kycore import Kycore

@pytest.fixture
def temp_db(tmp_path):
    db_file = tmp_path / "test_kydata.db"
    return str(db_file)

@pytest.fixture
def kv_store(temp_db):
    return Kycore(db_path=temp_db)

@pytest.fixture
def clean_home_db(tmp_path, monkeypatch):
    """Ensure a clean home directory and DB for each test."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr("os.path.expanduser", lambda x: str(fake_home / "kydata.db") if x == "~/kydata.db" else x)
    monkeypatch.setenv("HOME", str(fake_home))
    return fake_home
