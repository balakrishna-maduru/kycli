import os
import pytest
from kycli.config import load_config
import importlib

def test_config_env_variable(monkeypatch):
    monkeypatch.setenv("KYCLI_DB_PATH", "/tmp/env_db.db")
    config = load_config()
    assert config["db_path"] == "/tmp/env_db.db"

def test_config_tomli_fallback():
    import builtins
    real_import = builtins.__import__
    def mock_import(name, *args, **kwargs):
        if name == "tomllib": raise ImportError
        return real_import(name, *args, **kwargs)
    with patch("builtins.__import__", side_effect=mock_import):
        import kycli.config
        importlib.reload(kycli.config)

from unittest.mock import patch
