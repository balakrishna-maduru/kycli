import os
import sys
import json
import pytest
import runpy
import importlib
from unittest.mock import patch, MagicMock
from kycli.cli import main
from kycli.tui import KycliShell, start_shell
from kycli.config import load_config

def test_cli_save_status_nochange(clean_home_db):
    with patch("kycli.cli.Kycore") as mock_kv_class:
        mock_kv = MagicMock()
        mock_kv_class.return_value.__enter__.return_value = mock_kv
        mock_kv.getkey.return_value = "Key not found"
        mock_kv.save.return_value = "nochange"
        with patch("sys.argv", ["kys", "k", "v"]):
            main()

def test_tui_handler_coverage(tmp_path):
    with patch("kycli.tui.Kycore") as mock_kv_class:
        shell = KycliShell(db_path=str(tmp_path / "tui.db"))
        shell.app = MagicMock()
        mock_buffer = MagicMock()
        for binding in shell.kb.bindings:
            event = MagicMock()
            binding.handler(event)
        mock_buffer.text = "   "
        shell.handle_command(mock_buffer)
        mock_buffer.text = "kyv mykey"
        shell.kv.get_history.return_value = [("mykey", "val", "ts")]
        shell.handle_command(mock_buffer)
        mock_buffer.text = "kyc mycmd"
        shell.kv.getkey.return_value = "cmd"
        with patch("threading.Thread", side_effect=RuntimeError("thread fail")):
            shell.handle_command(mock_buffer)

def test_tui_app_run_coverage(tmp_path):
    with patch("kycli.tui.Kycore"):
        shell = KycliShell(db_path=str(tmp_path / "run.db"))
        with patch.object(shell.app, "run") as mock_run:
            shell.run()

def test_config_tomli_fallback():
    import builtins
    real_import = builtins.__import__
    def mock_import(name, *args, **kwargs):
        if name == "tomllib": raise ImportError
        return real_import(name, *args, **kwargs)
    with patch("builtins.__import__", side_effect=mock_import):
        import kycli.config
        importlib.reload(kycli.config)

def test_cli_main_entry_real():
    # Hit cli.py line 213
    # Use absolute path to match coverage calculation
    path = os.path.abspath("kycli/cli.py")
    with patch("sys.argv", ["kycli", "kyh"]):
        with patch("kycli.cli.Kycore"):
             try:
                 runpy.run_path(path, run_name="__main__")
             except SystemExit:
                 pass

def test_tui_new_commands_coverage(tmp_path):
    with patch("kycli.tui.Kycore"):
        shell = KycliShell(db_path=str(tmp_path / "new.db"))
        shell.app = MagicMock()
        mock_buffer = MagicMock()
        
        # Line 195: kyh
        mock_buffer.text = "kyh"
        shell.handle_command(mock_buffer)
        assert "Advanced Help" in shell.output_area.text
        
        # Line 197: kyshell
        mock_buffer.text = "kyshell"
        shell.handle_command(mock_buffer)
        assert "interactive shell" in shell.output_area.text

def test_config_env_variable(monkeypatch):
    monkeypatch.setenv("KYCLI_DB_PATH", "/tmp/env_db.db")
    config = load_config()
    assert config["db_path"] == "/tmp/env_db.db"
