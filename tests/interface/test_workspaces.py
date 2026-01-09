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
        
        mock_expand.side_effect = lambda p: str(tmp_path / "kydata.db") if p == "~/kydata.db" else (str(tmp_path / ".kyclirc") if p == "~/.kyclirc" else p)
        
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
    assert "alpha" in out
    assert "beta" in out
