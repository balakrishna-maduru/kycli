import os
import json
import pytest
from unittest.mock import patch, MagicMock
from kycli.config import load_config, save_config, DATA_DIR, KYCLI_DIR, CONFIG_PATH

@pytest.fixture
def clean_env(tmp_path):
    """Mock the home directory and data directory."""
    with patch("kycli.config.KYCLI_DIR", str(tmp_path / ".kycli")), \
         patch("kycli.config.DATA_DIR", str(tmp_path / ".kycli" / "data")), \
         patch("kycli.config.CONFIG_PATH", str(tmp_path / ".kycli" / "config.json")), \
         patch("os.path.expanduser") as mock_expand:
        
        def expand_path(p):
             if p == "~/kydata.db": return str(tmp_path / "kydata.db")
             if p == "~/.kyclirc": return str(tmp_path / ".kyclirc")
             if p == "~/.kyclirc.json": return str(tmp_path / ".kyclirc.json")
             return p
        mock_expand.side_effect = expand_path
        
        yield tmp_path

def test_migration_logic(clean_env):
    """Test that legacy DB is migrated to default.db."""
    # Setup legacy DB
    legacy_db = clean_env / "kydata.db"
    legacy_db.write_text("dummy sqlite content")
    
    # Run load_config which triggers migration
    config = load_config()
    
    # Check migration
    default_db = clean_env / ".kycli" / "data" / "default.db"
    assert not legacy_db.exists()
    assert default_db.exists()
    assert default_db.read_text() == "dummy sqlite content"
    assert config["db_path"] == str(default_db)

def test_workspace_isolation(clean_env, capsys):
    """Test saving keys in different workspaces."""
    from kycli.cli import main
    
    # 1. Save in default workspace
    with patch("sys.argv", ["kys", "k1", "val1"]): main()
    assert "Saved: k1" in capsys.readouterr().out
    
    # 2. Switch to 'project_a'
    with patch("sys.argv", ["kyuse", "project_a"]): main()
    assert "Switched to workspace: project_a" in capsys.readouterr().out
    
    # 3. Verify k1 is NOT here
    with patch("sys.argv", ["kyg", "k1"]): main()
    out = capsys.readouterr().out
    assert "Key not found" in out or "None" in out
    
    # 4. Save k2 in project_a
    with patch("sys.argv", ["kys", "k2", "val2"]): main()
    assert "Saved: k2" in capsys.readouterr().out
    
    # 5. Switch back to default
    with patch("sys.argv", ["kyuse", "default"]): main()
    
    # 6. Verify k1 exists and k2 does not
    with patch("sys.argv", ["kyg", "k1"]): main()
    assert "val1" in capsys.readouterr().out
    
    with patch("sys.argv", ["kyg", "k2"]): main()
    assert "Key not found" in capsys.readouterr().out

def test_workspace_move(clean_env, capsys):
    """Test moving a key between workspaces."""
    from kycli.cli import main
    
    # 1. Create source data in 'ws1'
    with patch("sys.argv", ["kyuse", "ws1"]): main()
    capsys.readouterr()
    with patch("sys.argv", ["kys", "move_me", "content"]): main()
    capsys.readouterr()
    
    # 2. Switch to 'ws2' to create the DB file (implicit creation on use? No, explicitly create it by saving something or just ensuring it exists)
    # The 'kymv' command initializes target DB, so we don't strictly need to switch first, but let's ensure it's valid.
    
    # 3. Move from 'ws1' to 'ws2' (while active is ws1)
    with patch("sys.argv", ["kymv", "move_me", "ws2"]): main()
    out = capsys.readouterr().out
    assert "Moved 'move_me' to 'ws2'" in out
    
    # 4. Verify gone from ws1
    with patch("sys.argv", ["kyg", "move_me"]): main()
    assert "Key not found" in capsys.readouterr().out
    
    # 5. Switch to ws2 and verify exists
    with patch("sys.argv", ["kyuse", "ws2"]): main()
    capsys.readouterr()
    with patch("sys.argv", ["kyg", "move_me"]): main()
    assert "content" in capsys.readouterr().out

def test_list_workspaces(clean_env, capsys):
    from kycli.cli import main
    
    # Create some DBs manually
    data_dir = clean_env / ".kycli" / "data"
    os.makedirs(data_dir, exist_ok=True)
    (data_dir / "alpha.db").touch()
    (data_dir / "beta.db").touch()
    
    with patch("sys.argv", ["kyws"]): main()
    out = capsys.readouterr().out
    assert "beta" in out

def test_config_env_override(clean_env):
    """Test that KYCLI_DB_PATH overrides active workspace."""
    custom_db = clean_env / "custom.db"
    with patch.dict(os.environ, {"KYCLI_DB_PATH": str(custom_db)}):
        config = load_config()
        assert config["db_path"] == str(custom_db)

def test_legacy_config_loading(clean_env):
    """Test loading from legacy .kyclirc files."""
    # Test JSON .kyclirc
    rc_path = clean_env / ".kyclirc.json"
    rc_path.write_text('{"export_format": "yaml"}')
    
    original_exists = os.path.exists
    def mock_exists(p):
        if str(p) == str(rc_path): return True
        return original_exists(p)

    with patch("os.path.exists", side_effect=mock_exists):
        config = load_config()
        assert config["export_format"] == "yaml"

def test_kyuse_validation(clean_env, capsys):
    from kycli.cli import main
    # Invalid name
    with patch("sys.argv", ["kyuse", "bad/name"]): main()
    assert "Invalid workspace name" in capsys.readouterr().out
    
    # Empty name (usage)
    with patch("sys.argv", ["kyuse"]): main()
    assert "Usage: kyuse" in capsys.readouterr().out

def test_kymv_errors(clean_env, capsys):
    from kycli.cli import main
    # 1. Target same as source
    with patch("sys.argv", ["kymv", "k1", "default"]): main()
    assert "same" in capsys.readouterr().out
    
    # 2. Key not found
    with patch("sys.argv", ["kymv", "missing_key", "target_ws"]): main()
    assert "not found" in capsys.readouterr().out
    
    # 3. Usage
    with patch("sys.argv", ["kymv"]): main()
    assert "Usage: kymv" in capsys.readouterr().out

def test_kymv_overwrite_abort(clean_env, capsys):
    from kycli.cli import main
    # Setup: key exists in both
    with patch("sys.argv", ["kyuse", "ws1"]): main()
    with patch("sys.argv", ["kys", "k1", "v1"]): main()
    capsys.readouterr()
    
    with patch("sys.argv", ["kyuse", "ws2"]): main()
    with patch("sys.argv", ["kys", "k1", "v2"]): main()
    capsys.readouterr()
    
    # Switch back to ws1
    with patch("sys.argv", ["kyuse", "ws1"]): main()
    capsys.readouterr()
    
    # Try move, input 'n' to abort
    with patch("sys.stdin.isatty", return_value=True):
        with patch("builtins.input", return_value="n"):
            with patch("sys.argv", ["kymv", "k1", "ws2"]): main()
            assert "Aborted" in capsys.readouterr().out

def test_kymv_overwrite_confirm(clean_env, capsys):
    from kycli.cli import main
    # Setup: key exists in both
    with patch("sys.argv", ["kyuse", "ws1"]): main()
    with patch("sys.argv", ["kys", "k1", "val_original"]): main()
    capsys.readouterr()
    
    with patch("sys.argv", ["kyuse", "ws2"]): main()
    with patch("sys.argv", ["kys", "k1", "val_conflict"]): main()
    capsys.readouterr()
    
    # Switch back to ws1
    with patch("sys.argv", ["kyuse", "ws1"]): main()
    capsys.readouterr()
    
    # Try move, input 'y' to confirm
    with patch("sys.stdin.isatty", return_value=True):
        with patch("builtins.input", return_value="y"):
            with patch("sys.argv", ["kymv", "k1", "ws2"]): main()
            out = capsys.readouterr().out
            assert "Moved 'k1'" in out
            
    # Verify ws2 has new value
    with patch("sys.argv", ["kyuse", "ws2"]): main()
    capsys.readouterr()
    with patch("sys.argv", ["kyg", "k1"]): main()
    assert "val_original" in capsys.readouterr().out

def test_lazy_workspace_creation(clean_env, capsys):
    from kycli.cli import main, load_config
    
    # Switch to new workspace
    with patch("sys.argv", ["kyuse", "lazy_ws"]): main()
    capsys.readouterr()
    
    # File should NOT exist yet
    db_path = clean_env / ".kycli" / "data" / "lazy_ws.db"
    assert not db_path.exists()
    
    # Save a key -> Creates file
    with patch("sys.argv", ["kys", "k", "v"]): main()
    capsys.readouterr()
    
    assert db_path.exists()

def test_pyproject_scripts(clean_env):
    """Ensure all CLI commands are registered in pyproject.toml."""
    # Locate pyproject.toml relative to tests
    root = clean_env.parent.parent # clean_env is tmp_path/home
    # Actually finding the real pyproject is safer via known path or just parsing the one in repo
    # But clean_env moves us to tmp.
    # We can assume the test runner CWD is the project root (standard pytest behavior)
    import tomli
    
    pyproject_path = "pyproject.toml"
    if not os.path.exists(pyproject_path):
        pytest.skip("pyproject.toml not found in CWD")
        
    with open(pyproject_path, "rb") as f:
        data = tomli.load(f)
        
    scripts = data["tool"]["poetry"]["scripts"]
    required = ["kyuse", "kyws", "kymv", "kycli", "kys", "kyg"]
    for req in required:
        assert req in scripts, f"Missing script '{req}' in pyproject.toml"
