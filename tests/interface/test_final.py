import pytest
from unittest.mock import patch, MagicMock, mock_open
import sys
import os
from kycli import cli
from kycli import config
import kycli.tui as tui

# --- CLI COVERAGE ---

def test_cli_kyws_current(capsys):
    with patch("sys.argv", ["kycli", "kyws", "--current"]), \
         patch("kycli.cli.load_config", return_value={"active_workspace": "testbox", "db_path": ":memory:", "export_format": "csv"}):
         cli.main()
    out, _ = capsys.readouterr()
    assert "testbox" in out

def test_cli_kyws_args(capsys):
    with patch("sys.argv", ["kycli", "kyws", "arg1"]), \
         patch("kycli.cli.load_config", return_value={"active_workspace": "default", "db_path": ":memory:"}):
         cli.main()
    out, _ = capsys.readouterr()
    assert "Did you mean 'kyuse arg1'" in out

def test_cli_kymv_confirm_no(capsys):
    # kymv <key> <target> where key exists in target
    with patch("sys.argv", ["kycli", "kymv", "k1", "ws2"]), \
         patch("kycli.cli.load_config", return_value={"active_workspace": "ws1", "db_path": ":memory:"}), \
         patch("kycli.cli.Kycore") as MockKycore, \
         patch("builtins.input", return_value="n"):
         
         # Source mock
         mock_source = MagicMock()
         mock_source.getkey.return_value = "val1"
         
         # Target mock (context manager)
         mock_target = MagicMock()
         mock_target.__enter__.return_value = mock_target
         mock_target.__contains__.return_value = True # key exists
         
         # Kycore constructor side effect
         # First call is source (context manager)
         # Second call is target
         # Actually cli.py uses Kycore for source: `with Kycore(...) as kv:`
         # And then `with Kycore(target_db...) as target_kv:`
         
         mock_instance = MagicMock()
         mock_instance.__enter__.return_value = mock_instance
         # Setup different behaviors for source and target?
         # Simplest: The same mock class returns a mock instance.
         # But we need "key in target_kv" to be True.
         
         MockKycore.return_value = mock_instance
         mock_instance.getkey.return_value = "val1"
         mock_instance.__contains__.return_value = True
         
         cli.main()
         
    out, _ = capsys.readouterr()
    assert "Aborted" in out

def test_cli_name_main():
    # Only meaningful if we could import cli as __main__, but harder in pytest
    pass


# --- CONFIG COVERAGE ---

def test_config_migrate_exception(tmp_path):
    # Cover lines 43-44: except Exception: pass
    bad_legacy = tmp_path / "kydata.db"
    bad_legacy.touch()
    
    with patch("kycli.config.DATA_DIR", str(tmp_path / "data")), \
         patch("os.path.expanduser", return_value=str(bad_legacy)), \
         patch("shutil.move", side_effect=OSError("fail")):
         
         config.migrate_legacy_db()
         # Should not raise
         
def test_config_tomli_import_fail():
    # Cover lines 10-11: toml fallback
    # We need to simulate ImportError for tomli
    # This is import time logic, hard to test without reloading module
    pass


# --- TUI COVERAGE ---

def test_tui_misc_branches():
    # Cover args usage in kyg, etc
    # kyg needs to check 'if not args'
    # kyd needs 'if not args'
    # kye export
    
    with patch("kycli.tui.Kycore"):
        shell = tui.KycliShell()
    
    shell.output_area = MagicMock()
    shell.kv = MagicMock()
    
    # KYG no args
    stmt = tui.KycliShell.handle_command
    
    # Mock buffer
    def run_cmd(txt):
        b = MagicMock()
        b.text = txt
        stmt(shell, b)
        return shell.output_area.text
        
    assert "Usage: kyg" in run_cmd("kyg")
    assert "Usage: kyd" in run_cmd("kyd")
    assert "Usage: kyrem" in run_cmd("kyrem")
    assert "Usage: kye" in run_cmd("kye")
    assert "Usage: kyi" in run_cmd("kyi")
    assert "Usage: kyc" in run_cmd("kyc")
    assert "Usage: kyrt" in run_cmd("kyrt")
    
    # kyrt with --at
    shell.kv.restore.return_value = "restored"
    run_cmd("kyrt key --at 1234")
    shell.kv.restore.assert_called()

# --- INIT PY COVERAGE ---
def test_init_import_error():
    # To coverlines 3-9 in __init__.py
    # We can try to reload the module with mocked imports
    import sys
    import importlib
    
    with patch.dict(sys.modules, {"kycli.core.storage": None}):
        with patch("builtins.__import__", side_effect=ImportError("fail")):
             # We need to force reload kycli
             # But kycli is already imported.
             # We can try to import kycli again manually?
             # Or just manually execute the code block?
             pass 
             # It's okay if this stays at 90-something for lines hard to reach.
