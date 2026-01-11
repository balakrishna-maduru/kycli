import os
import sys
import json
import pytest
from unittest.mock import patch, MagicMock, mock_open

# --- Gap Coverage Tests for kycli/config.py ---

def test_config_save_exception(tmp_path):
    from kycli.config import save_config
    with patch("kycli.config.CONFIG_PATH", str(tmp_path / "protected" / "config.json")):
        # Ensure dir exists but file is unwritable or open raises
        with patch("builtins.open", side_effect=PermissionError("Boom")):
            # Should not raise
            save_config({"foo": "bar"})

def test_config_load_json_error(tmp_path):
    from kycli.config import load_raw_config
    p = tmp_path / "config.json"
    p.write_text("{badjson")
    with patch("kycli.config.CONFIG_PATH", str(p)):
        # exception handling in load_raw_config
        c = load_raw_config()
        assert c.get("active_workspace") == "default"

def test_migrate_exception(tmp_path):
    from kycli.config import migrate_legacy_db, DATA_DIR
    legacy = tmp_path / "kydata.db"
    legacy.write_text("data")
    
    with patch("os.path.expanduser", return_value=str(legacy)):
        # Force shutil.move to fail
        with patch("shutil.move", side_effect=OSError("Disk full")):
            migrate_legacy_db()
            # Should silently fail/pass

def test_toml_import_logic():
    # It's hard to mock the import itself in a running process without reload
    # But we can test the fallback loop in load_raw_config
    from kycli.config import load_raw_config
    
    with patch("kycli.config.toml", new=None):
         # If toml is None, it shouldn't try to load .kyclirc using toml
         # But if checking .json extension it uses json
         pass

# --- Gap Coverage Tests for kycli/cli.py ---

def test_cli_move_exception(capsys):
    from kycli.cli import main
    # trigger exception in kymv block (e.g. key checking fails)
    with patch("sys.argv", ["kymv", "k", "pool"]):
        with patch("kycli.cli.Kycore") as mock_kv:
            # First instance ok
            inst = mock_kv.return_value
            inst.__enter__.return_value = inst
            inst.getkey.return_value = "val"
            
            # Inner Kycore raises
            mock_kv.side_effect = [inst, Exception("Connect failed")]
            
            main()
            assert "Failed to move" in capsys.readouterr().out

def test_cli_execution_error(capsys):
    from kycli.cli import main
    with patch("sys.argv", ["kyc", "key"]):
         with patch("kycli.cli.Kycore") as mock_kv:
            inst = mock_kv.return_value
            inst.__enter__.return_value = inst
            inst.getkey.return_value = "ls"
            
            with patch("subprocess.run", side_effect=Exception("Exec failed")):
                main()
                assert "Execution Error" in capsys.readouterr().out

# --- Gap Coverage Tests for kycli/tui.py ---

def test_tui_gaps(tmp_path):
    from kycli.tui import KycliShell
    from kycli import Kycore
    
    with patch("kycli.tui.Kycore") as mock_kv_cls:
        shell = KycliShell()
        shell.app = MagicMock()
        mock_buf = MagicMock()
        
        # 1. kyg --limit parser
        mock_buf.text = "kyg -s q --limit 10"  # limit is int
        shell.handle_command(mock_buf)
        mock_kv_cls.return_value.search.assert_called_with("q", limit=10, keys_only=False)
        
        # 2. kyg --limit bad (should be skipped/ignored or handeled?)
        # code: try: limit = int(...) except: pass
        mock_buf.text = "kyg -s q --limit bad"
        shell.handle_command(mock_buf)
        # Should likely default to 100
        
        # 3. kyg --keys-only
        mock_buf.text = "kyg -s q --keys-only"
        shell.handle_command(mock_buf)
        mock_kv_cls.return_value.search.assert_called_with("q", limit=100, keys_only=True)
        
        # 4. kyg result list/dict rendering
        mock_kv_cls.return_value.getkey.return_value = {"a": 1}
        mock_buf.text = "kyg k"
        shell.handle_command(mock_buf)
        assert "{" in shell.output_area.text
        
        # 5. kypush json
        mock_buf.text = 'kypush k {"a":1}'
        shell.handle_command(mock_buf)
        mock_kv_cls.return_value.push.assert_called_with("k", {"a":1}, unique=False)
        
        # 6. kyrem json (arg parsing)
        mock_buf.text = 'kyrem k {"a":1}'
        shell.handle_command(mock_buf)
        
        # 7. update_history exception
        # Force get_history to raise
        shell.kv.get_history.side_effect = Exception("DB Lock")
        shell.update_history()
        assert "Error loading" in shell.history_area.text

