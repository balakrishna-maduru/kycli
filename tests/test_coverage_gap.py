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

def test_cli_global_flags_coverage(clean_home_db):
    with patch("kycli.cli.Kycore") as mock_kv_class:
        mock_kv = mock_kv_class.return_value.__enter__.return_value
        mock_kv.getkey.return_value = "Key not found"
        with patch("sys.argv", ["kycli", "kys", "mykey", "myval", "--key", "mypass", "--ttl", "1h"]):
            main()
        # Verify master_key was passed to Kycore and ttl to save
        mock_kv_class.assert_called()
        mock_kv.save.assert_called()
        # Check that 'mypass' was used
        args, kwargs = mock_kv_class.call_args
        assert kwargs.get('master_key') == 'mypass'

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
        assert "Available commands" in shell.output_area.text
        
        # Line 197: kyshell
        mock_buffer.text = "kyshell"
        shell.handle_command(mock_buffer)
        assert "interactive shell" in shell.output_area.text

        # Test flags in kys and kyg for coverage (Line 149-164, 175-177)
        mock_buffer.text = "kys mykey myval --ttl 10s --key mypass"
        shell.handle_command(mock_buffer)
        assert "Saved" in shell.output_area.text

        mock_buffer.text = "kyg mykey --key mypass"
        shell.handle_command(mock_buffer)
        
        # Test missing args for kye (Line 219)
        mock_buffer.text = "kye"
        shell.handle_command(mock_buffer)
        assert "Usage" in shell.output_area.text

        # Test kyc with multiple args (Line 241)
        shell.kv.getkey.return_value = "echo"
        mock_buffer.text = "kyc mykey extra_arg"
        with patch("threading.Thread") as mock_thread:
            shell.handle_command(mock_buffer)
            assert mock_thread.called
            assert "Started: echo extra_arg" in shell.output_area.text

        # Test missing history (Line 211)
        shell.kv.get_history.return_value = []
        mock_buffer.text = "kyv non_existent"
        shell.handle_command(mock_buffer)
        assert "No history for non_existent" in shell.output_area.text

        # Test warning display (Line 257-258)
        def mock_warn_getkey(k, **kwargs):
            import warnings
            warnings.warn("test warning", UserWarning)
            return "val"
        
        shell.kv.getkey.side_effect = mock_warn_getkey
        mock_buffer.text = "kyg somekey"
        shell.handle_command(mock_buffer)
        assert "⚠️ test warning" in shell.output_area.text
        shell.kv.getkey.side_effect = None

        # Test kyh coverage specifically (Line 246)
        mock_buffer.text = "kyh"
        shell.handle_command(mock_buffer)
        assert "Available commands" in shell.output_area.text

def test_tui_start_shell_coverage():
    # Hit start_shell lines (267-269)
    with patch("kycli.tui.KycliShell") as mock_shell_class:
        mock_shell_inst = mock_shell_class.return_value
        start_shell("/tmp/dummy.db")
        mock_shell_class.assert_called_once_with("/tmp/dummy.db")
        mock_shell_inst.run.assert_called_once()

def test_config_env_variable(monkeypatch):
    monkeypatch.setenv("KYCLI_DB_PATH", "/tmp/env_db.db")
    config = load_config()
    assert config["db_path"] == "/tmp/env_db.db"
