import os
import pytest
from kycli.core.storage import Kycore

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
    
    # Patch module-level constants in kycli.config since they are loaded at import time
    fake_kycli_dir = fake_home / ".kycli"
    fake_data_dir = fake_kycli_dir / "data"
    fake_config_path = fake_kycli_dir / "config.json"
    
    # We need to mock them wherever they are imported
    # But usually patching kycli.config is enough if others use `from kycli import config` or `config.DATA_DIR`
    monkeypatch.setattr("kycli.config.KYCLI_DIR", str(fake_kycli_dir))
    monkeypatch.setattr("kycli.config.DATA_DIR", str(fake_data_dir))
    monkeypatch.setattr("kycli.config.CONFIG_PATH", str(fake_config_path))

    monkeypatch.setattr("os.path.expanduser", lambda x: str(fake_home / "kydata.db") if x == "~/kydata.db" else (str(fake_home / ".kyclirc") if x == "~/.kyclirc" else (str(fake_home) if x == "~" else x)))
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.delenv("KYCLI_DB_PATH", raising=False)
    return fake_home
