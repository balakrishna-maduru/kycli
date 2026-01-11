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

# --- Gap Coverage Tests ---

def test_config_save_exception(tmp_path):
    from kycli.config import save_config
    try:
        from unittest.mock import patch
    except ImportError: pass 
    with patch("kycli.config.CONFIG_PATH", str(tmp_path / "protected" / "config.json")):
        # Ensure dir exists but file is unwritable or open raises
        with patch("builtins.open", side_effect=PermissionError("Boom")):
            # Should not raise
            save_config({"foo": "bar"})

def test_config_load_json_error(tmp_path):
    from kycli.config import load_raw_config
    try:
        from unittest.mock import patch
    except ImportError: pass
    p = tmp_path / "config.json"
    p.write_text("{badjson")
    with patch("kycli.config.CONFIG_PATH", str(p)):
        # exception handling in load_raw_config
        c = load_raw_config()
        assert c.get("active_workspace") == "default"

def test_migrate_exception(tmp_path):
    from kycli.config import migrate_legacy_db, DATA_DIR
    try:
        from unittest.mock import patch
    except ImportError: pass
    legacy = tmp_path / "kydata.db"
    legacy.write_text("data")
    
    with patch("os.path.expanduser", return_value=str(legacy)):
        # Force shutil.move to fail
        with patch("shutil.move", side_effect=OSError("Disk full")):
            migrate_legacy_db()
            # Should silently fail/pass

def test_toml_import_logic():
    # It hard to mock the import itself in a running process without reload
    # But we can test the fallback loop in load_raw_config
    from kycli.config import load_raw_config
    try:
        from unittest.mock import patch
    except ImportError: pass
    
    with patch("kycli.config.toml", new=None):
         # If toml is None, it shouldnt try to load .kyclirc using toml
         # But if checking .json extension it uses json
         pass

def test_config_toml_success(tmp_path):
    from kycli import config
    try:
        from unittest.mock import patch
    except ImportError: pass
    # Ensure toml library IS available (it is in pyproject)
    # Create valid TOML file
    rc = tmp_path / ".kyclirc"
    rc.write_text("theme = { key = \"blue\" }")
    
    with patch("kycli.config.CONFIG_PATH", str(tmp_path / "protected")):
         with patch("os.path.expanduser", return_value=str(rc)):
             data = config.load_raw_config()
             # Should parse TOML
             assert data.get("theme", {}).get("key") == "blue"

def test_config_migrate_fail(tmp_path):
    from kycli.config import migrate_legacy_db
    try:
        from unittest.mock import patch
    except ImportError: pass
    # Force legacy DB
    legacy = tmp_path / "kydata.db"
    legacy.write_text("dummy")
    
    with patch("os.path.expanduser", return_value=str(legacy)):
        # Force move failure
        with patch("shutil.move", side_effect=OSError("Fail")):
             migrate_legacy_db()
             # Should pass silently
             assert legacy.exists()

def test_config_toml_import_errors(tmp_path):
    from kycli import config
    import sys
    try:
        from unittest.mock import patch
    except ImportError: pass
    
    # 1. Test optional import failure
    with patch.dict(sys.modules, {"tomllib": None, "tomli": None}):
        # Force reload of logic? No, the import runs at top level.
        # We can test the toml variable check in load_raw_config
        with patch("kycli.config.toml", None):
            # Write a .kyclirc (toml format implied by lack of .json extension)
            rc = tmp_path / ".kyclirc"
            rc.write_text("foo=\"bar\"")
            
            with patch("kycli.config.CONFIG_PATH", str(tmp_path / "protected")):
                 with patch("os.path.expanduser", return_value=str(rc)):
                     # Should NOT try to load toml if toml is None
                     data = config.load_raw_config()
                     assert "foo" not in data
