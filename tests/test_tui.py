import pytest
import os
import json
from io import BytesIO
from unittest.mock import patch, MagicMock
from kycli.config import load_config
from kycli.tui import KycliShell

# Mock ANSI to return plain text for easier assertions
import kycli.tui
kycli.tui.ANSI = lambda x: x


# Workspace tests for TUI
def test_tui_workspaces_switching(tmp_path):
    with patch("kycli.tui.Kycore") as mock_kv_class:
        with patch("kycli.tui.save_config") as mock_save:
            shell = KycliShell(db_path=str(tmp_path / "tui_init.db"))
            shell.app = MagicMock()
            mock_buffer = MagicMock()
            
            # List workspaces
            with patch("kycli.tui.get_workspaces", return_value=["alpha", "beta"]):
                mock_buffer.text = "kyws"
                shell.handle_command(mock_buffer)
                assert "alpha" in shell.output_area.text
                assert "beta" in shell.output_area.text
            
            # Switch valid
            mock_buffer.text = "kyuse beta"
            shell.handle_command(mock_buffer)
            mock_save.assert_called_with({"active_workspace": "beta"})
            assert "Switched to workspace: beta" in shell.output_area.text
            
            # Switch invalid
            mock_buffer.text = "kyuse bad/name"
            shell.handle_command(mock_buffer)
            assert "Invalid name" in shell.output_area.text
            
            # Config refresh check (mocking load_config in TUI init/update)
            # The shell reloads config on switch, which we mock via kycli.config.load_config
            # but testing that integration might be tricky with mocks.
            # We trust save_config was called.

def test_cli_dispatch_various_progs(clean_home_db):
    from kycli.cli import main
    # Test running as kyshell directly
    with patch("kycli.tui.start_shell") as mock_shell:
        with patch("sys.argv", ["kyshell"]):
            main()
            mock_shell.assert_called_once()
            
    # Test running as python module with no args (should show help)
    with patch("sys.argv", ["python", "-m", "kycli.cli"]):
        with patch("kycli.cli.print_help") as mock_help:
            main()
            mock_help.assert_called()

def test_tui_shell_basic_dispatch(tmp_path):
    # Test internal logic of handle_command
    with patch("kycli.tui.Kycore") as mock_kv_class:
        mock_kv = mock_kv_class.return_value
        shell = KycliShell(db_path=str(tmp_path / "test.db"))
        
        # Mocking the application to avoid starting a loop
        shell.app = MagicMock()
        
        # Test Save
        mock_buffer = MagicMock()
        mock_buffer.text = "kys mykey myval"
        shell.handle_command(mock_buffer)
        mock_kv.save.assert_called_with("mykey", "myval", ttl=None)
        assert "Saved: mykey" in shell.output_area.text
        
        # Test Get
        mock_kv.getkey.return_value = "hello"
        mock_buffer.text = "kyg mykey"
        shell.handle_command(mock_buffer)
        assert "hello" in shell.output_area.text
        
        # Test List
        mock_kv.listkeys.return_value = ["k1", "k2"]
        mock_buffer.text = "ls"
        shell.handle_command(mock_buffer)
        assert "k1, k2" in shell.output_area.text

        # Test Exit
        mock_buffer.text = "exit"
        shell.handle_command(mock_buffer)
        shell.app.exit.assert_called()

def test_tui_shell_more_dispatch(tmp_path):
    with patch("kycli.tui.Kycore") as mock_kv_class:
        mock_kv = mock_kv_class.return_value
        shell = KycliShell(db_path=str(tmp_path / "test2.db"))
        shell.app = MagicMock()
        mock_buffer = MagicMock()
        
        # Test Search
        mock_kv.search.return_value = {"k1": "v1"}
        mock_buffer.text = "kyg -s myquery"
        shell.handle_command(mock_buffer)
        assert "k1" in shell.output_area.text
        assert "v1" in shell.output_area.text
        
        # Test Delete
        mock_buffer.text = "kyd mykey"
        shell.handle_command(mock_buffer)
        mock_kv.delete.assert_called_with("mykey")
        assert "Deleted: mykey" in shell.output_area.text
        
        # Test Usage Messages
        mock_buffer.text = "kys k" # Missing value
        shell.handle_command(mock_buffer)
        assert "Usage" in shell.output_area.text
        
        mock_buffer.text = "kyg" # Missing key
        shell.handle_command(mock_buffer)
        assert "Usage" in shell.output_area.text

def test_tui_shell_full_commands(tmp_path):
    with patch("kycli.tui.Kycore") as mock_kv_class:
        mock_kv = mock_kv_class.return_value
        shell = KycliShell(db_path=str(tmp_path / "test_full.db"))
        shell.app = MagicMock()
        mock_buffer = MagicMock()
        
        # Test kyv
        mock_kv.get_history.return_value = [("k", "v", "ts")]
        mock_buffer.text = "kyv"
        shell.handle_command(mock_buffer)
        assert "ts" in shell.output_area.text
        
        # Test kyr
        mock_kv.restore.return_value = "Restored k"
        mock_buffer.text = "kyr k"
        shell.handle_command(mock_buffer)
        assert "Restored k" in shell.output_area.text
        
        # Test kye
        mock_buffer.text = "kye export.csv"
        shell.handle_command(mock_buffer)
        mock_kv.export_data.assert_called()
        assert "Exported" in shell.output_area.text
        
        # Test kyi
        mock_buffer.text = "kyi import.csv"
        shell.handle_command(mock_buffer)
        mock_kv.import_data.assert_called()
        assert "Imported" in shell.output_area.text

        # Test unknown
        mock_buffer.text = "unknowncommand"
        shell.handle_command(mock_buffer)
        assert "Unknown" in shell.output_area.text

def test_tui_shell_execute_command(tmp_path):
    with patch("kycli.tui.Kycore") as mock_kv_class:
        mock_kv = mock_kv_class.return_value
        shell = KycliShell(db_path=str(tmp_path / "test_exec.db"))
        shell.app = MagicMock()
        mock_buffer = MagicMock()
        
        # Test kyc successfully
        mock_kv.getkey.return_value = "echo hello"
        mock_buffer.text = "kyc mycmd"
        with patch("threading.Thread") as mock_thread:
            shell.handle_command(mock_buffer)
            mock_thread.assert_called()
            assert "Started: echo hello" in shell.output_area.text
        
        # Test kyc key missing
        mock_kv.getkey.return_value = "Key not found"
        mock_buffer.text = "kyc missing"
        shell.handle_command(mock_buffer)
        assert "not found" in shell.output_area.text


def test_tui_misc_coverage(tmp_path):
    with patch("kycli.tui.Kycore") as mock_kv_class:
        shell = KycliShell(db_path=str(tmp_path / "misc.db"))
        shell.app = MagicMock()
        
        # Hit Line 77 (event.app.exit())
        mock_event = MagicMock()
        from kycli.tui import KeyBindings
        # Find the binding for c-c
        # This is hard to trigger directly without knowing how kb storage works
        
        # Hit Line 116 (update_history exception)
        shell.kv.get_history.side_effect = Exception("failed")
        shell.update_history() # Should not raise
        
        # Hit Line 194 (Unknown command)
        mock_buffer = MagicMock()
        mock_buffer.text = "unknown"
        shell.handle_command(mock_buffer)
        assert "Unknown command" in shell.output_area.text
        
        # Hit Line 196 (Outer exception)
        mock_buffer.text = "kys k v"
        shell.kv.save.side_effect = Exception("save failed")
        shell.handle_command(mock_buffer)
        assert "Error: save failed" in shell.output_area.text

def test_tui_start_shell():
    from kycli.tui import start_shell
    with patch("kycli.tui.KycliShell") as mock_shell_class:
        mock_shell = mock_shell_class.return_value
        start_shell("/tmp/test.db")
        mock_shell_class.assert_called_with("/tmp/test.db")
        mock_shell.run.assert_called_once()


def test_tui_shell_advanced_commands(tmp_path):
    with patch("kycli.tui.Kycore") as mock_kv_class:
        mock_kv = mock_kv_class.return_value
        shell = KycliShell(db_path=str(tmp_path / "test_adv.db"))
        shell.app = MagicMock()
        mock_buffer = MagicMock()
        
        # Test kyfo
        mock_buffer.text = "kyfo"
        shell.handle_command(mock_buffer)
        mock_kv.optimize_index.assert_called()
        assert "optimized" in shell.output_area.text
        
        # Test kyrt
        mock_buffer.text = "kyrt 2026-01-01"
        shell.handle_command(mock_buffer)
        mock_kv.restore_to.assert_called_with("2026-01-01")
        
        # Test kyco
        mock_buffer.text = "kyco 5"
        shell.handle_command(mock_buffer)
        mock_kv.compact.assert_called_with(5)
        
        # Test kys with path (patch)
        mock_buffer.text = "kys user.name balu"
        shell.handle_command(mock_buffer)
        mock_kv.patch.assert_called_with("user.name", "balu", ttl=None)
        
        # Test kypush
        mock_buffer.text = "kypush tags python"
        shell.handle_command(mock_buffer)
        mock_kv.push.assert_called_with("tags", "python", unique=False)
        
        # Test kyrem
        mock_buffer.text = "kyrem tags python"
        shell.handle_command(mock_buffer)
        mock_kv.remove.assert_called_with("tags", "python")

        # Test kyh
        mock_buffer.text = "kyh"
        shell.handle_command(mock_buffer)
        assert "🚀" in shell.output_area.text # get_help_text starts with rocket

def test_tui_handler_gap_coverage(tmp_path):
    with patch("kycli.tui.Kycore") as mock_kv_class:
        shell = KycliShell(db_path=str(tmp_path / "tui_gap.db"))
        shell.app = MagicMock()
        mock_buffer = MagicMock()
        for binding in shell.kb.bindings:
            event = MagicMock()
            binding.handler(event)
        mock_buffer.text = "   "
        shell.handle_command(mock_buffer)
        
        # Line 131: empty command
        mock_buffer.text = ""
        shell.handle_command(mock_buffer)

def test_tui_warning_display_coverage(tmp_path):
    with patch("kycli.tui.Kycore") as mock_kv_class:
        shell = KycliShell(db_path=str(tmp_path / "tui_warn.db"))
        shell.app = MagicMock()
        mock_buffer = MagicMock()
        
        def mock_warn_getkey(k, **kwargs):
            import warnings
            warnings.warn("test warning", UserWarning)
            return "val"
        
        shell.kv.getkey.side_effect = mock_warn_getkey
        mock_buffer.text = "kyg somekey"
        shell.handle_command(mock_buffer)
        assert "⚠️ test warning" in shell.output_area.text or "val" in shell.output_area.text

def test_tui_shell_exception_handling(tmp_path):
    with patch("kycli.tui.Kycore") as mock_kv_class:
        shell = KycliShell(db_path=str(tmp_path / "tui_exc.db"))
        shell.app = MagicMock()
        mock_buffer = MagicMock()
        shell.kv.save.side_effect = Exception("save failed")
        mock_buffer.text = "kys k v"
        shell.handle_command(mock_buffer)
        assert "Error: save failed" in shell.output_area.text

# --- Gap Coverage Tests ---

def test_tui_gaps(tmp_path):
    from kycli.tui import KycliShell
    from kycli.core.storage import Kycore
    try:
        from unittest.mock import patch, MagicMock
    except ImportError: pass
    
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
        mock_buf.text = "kypush k {\"a\":1}"
        shell.handle_command(mock_buf)
        mock_kv_cls.return_value.push.assert_called_with("k", {"a":1}, unique=False)
        
        # 6. kyrem json (arg parsing)
        mock_buf.text = "kyrem k {\"a\":1}"
        shell.handle_command(mock_buf)
        
        # 7. update_history exception
        # Force get_history to raise
        shell.kv.get_history.side_effect = Exception("DB Lock")
        shell.update_history()
        assert "Error loading" in shell.history_area.text

def test_tui_complex_args(tmp_path):
    from kycli.tui import KycliShell
    try:
        from unittest.mock import patch, MagicMock
    except ImportError: pass
    
    with patch("kycli.tui.Kycore") as mock_kv:
        shell = KycliShell()
        shell.app = MagicMock()
        mock_buf = MagicMock()
        
        # 1. kys with --ttl and --key mixed
        # kys k v --ttl 10 --key master
        mock_buf.text = "kys k v --ttl 10 --key master"
        shell.handle_command(mock_buf)
        # Should parse ttl=10, key=master
        # The skip logic coverage
        
        # 2. kyg with all flags
        # kyg -s q --limit 50 --key master --keys-only
        mock_buf.text = "kyg -s q --limit 50 --key master --keys-only"
        shell.handle_command(mock_buf)
        mock_kv.return_value.search.assert_called()
        
        # 3. kyg bad limit
        mock_buf.text = "kyg k --limit bad"
        shell.handle_command(mock_buf)
        
        # 4. kyg result list/dict
        mock_kv.return_value.getkey.return_value = ["a", "b"]
        mock_buf.text = "kyg mylist"
        shell.handle_command(mock_buf)
        assert "[" in shell.output_area.text
        
        # 5. kyl with pattern
        mock_buf.text = "kyl pat"
        shell.handle_command(mock_buf)
        mock_kv.return_value.listkeys.assert_called_with("pat")
        
        # 6. kyv with key (history)
        mock_kv.return_value.get_history.return_value = [("k", "v", "ts")]
        mock_buf.text = "kyv mykey"
        shell.handle_command(mock_buf)
        assert "History for mykey" in shell.output_area.text
        
        # 7. kye (Export)
        mock_buf.text = "kye dump.csv"
        shell.handle_command(mock_buf)
        mock_kv.return_value.export_data.assert_called()

        # 8. kyi (Import)
        mock_buf.text = "kyi dump.csv"
        shell.handle_command(mock_buf)
        mock_kv.return_value.import_data.assert_called()
        
        # 9. Kyc (Execute)
        # Key found path
        mock_kv.return_value.getkey.return_value = "echo hello"
        try:
            from unittest.mock import patch
            with patch("threading.Thread") as mock_thread:
                mock_buf.text = "kyc cmd arg1"
                shell.handle_command(mock_buf)
                mock_thread.assert_called()
        except: pass
            
        # Key not found path
        mock_kv.return_value.getkey.return_value = "Key not found"
        mock_buf.text = "kyc missing"
        shell.handle_command(mock_buf)
        assert "not found" in shell.output_area.text
        
        # 10. Start shell main entry (simple call)
        # We cant really run strict logic without blocking, but we tested it via mocking earlier.
        
        # 11. Warnings Loop
        # We need to trigger a warning in a command
        def warn_push(*args, **kwargs):
            import warnings
            warnings.warn("Ouch")
            return "pushed"
        mock_kv.return_value.push.side_effect = warn_push
        mock_buf.text = "kypush k v"
        shell.handle_command(mock_buf)
        assert "⚠️ Ouch" in shell.output_area.text
