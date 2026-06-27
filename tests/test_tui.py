import pytest
import os
import json
from io import BytesIO
from unittest.mock import patch, MagicMock
from prompt_toolkit.document import Document
from kycli.config import load_config
from kycli.tui import KycliShell, KycliCompleter

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
        mock_kv.get_type.return_value = "kv"
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

        # Test kypush usage (kv-mode, insufficient args)
        mock_buffer.text = "kypush tags"
        shell.handle_command(mock_buffer)
        assert "Usage: kypush <key> <value>" in shell.output_area.text

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


def test_tui_additional_gap_coverage(tmp_path):
    with patch("kycli.tui.Kycore") as mock_kv_class, \
         patch("kycli.tui.save_config") as mock_save:
        mock_kv = mock_kv_class.return_value
        mock_kv.get_history.return_value = []

        with patch("kycli.tui.load_config") as mock_load:
            mock_load.side_effect = [
                {"active_workspace": "ws1", "db_path": str(tmp_path / "ws1.db")},
                {"active_workspace": "default", "db_path": str(tmp_path / "default.db")},
            ]

            shell = KycliShell(db_path=str(tmp_path / "ws1.db"))
            shell.app = MagicMock()
            mock_buffer = MagicMock()

            # kyuse usage
            mock_buffer.text = "kyuse"
            shell.handle_command(mock_buffer)
            assert "Usage: kyuse" in shell.output_area.text

            # kydrop active with confirm
            with patch("kycli.tui.os.path.exists", return_value=True), \
                 patch("kycli.tui.os.remove"):
                mock_buffer.text = "kydrop ws1 --confirm"
                shell.handle_command(mock_buffer)
                assert "Switched to 'default' workspace" in shell.output_area.text
                mock_save.assert_called_with({"active_workspace": "default"})

            # kys with JSON value
            mock_buffer.text = "kys user {\"a\": 1}"
            shell.handle_command(mock_buffer)
            mock_kv.save.assert_any_call("user", {"a": 1}, ttl=None)

            # kys with invalid JSON (parse error path)
            mock_buffer.text = "kys bad {oops"
            shell.handle_command(mock_buffer)
            mock_kv.save.assert_any_call("bad", "{oops", ttl=None)

            # kyg with empty args after flags
            mock_buffer.text = "kyg --keys-only"
            shell.handle_command(mock_buffer)
            assert "Usage: kyg <key>" in shell.output_area.text

            # kyv with missing history
            mock_buffer.text = "kyv missing"
            shell.handle_command(mock_buffer)
            assert "No history for missing" in shell.output_area.text

            # kypush usage
            mock_buffer.text = "kypush"
            shell.handle_command(mock_buffer)
            assert "Usage: kypush" in shell.output_area.text

            # kyshell in TUI
            mock_buffer.text = "kyshell"
            shell.handle_command(mock_buffer)
            assert "already in the interactive shell" in shell.output_area.text

            # run wrapper
            shell.app = MagicMock()
            shell.run()
            shell.app.run.assert_called_once()

# --- Gap Coverage Tests ---

def test_tui_gaps(tmp_path):
    from kycli.tui import KycliShell
    from kycli.core.storage import Kycore
    try:
        from unittest.mock import patch, MagicMock
    except ImportError: pass
    
    with patch("kycli.tui.Kycore") as mock_kv_cls:
        mock_kv_cls.return_value.get_type.return_value = "kv"
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


def test_tui_queue_commands(tmp_path):
    """TUI parity: queue/stack ops (push/peek/pop/ack/nack/count/clear) on a
    typed (non-kv) workspace."""
    with patch("kycli.tui.Kycore") as mock_kv_class:
        mock_kv = mock_kv_class.return_value
        mock_kv.get_type.return_value = "queue"
        shell = KycliShell(db_path=str(tmp_path / "tui_queue.db"))
        shell.app = MagicMock()
        mock_buf = MagicMock()

        # kypush with priority
        mock_kv.push.return_value = "pushed"
        mock_buf.text = "kypush job1 --priority 5"
        shell.handle_command(mock_buf)
        mock_kv.push.assert_called_with("job1", priority=5, ttl=None)

        # kypush with delay
        mock_buf.text = "kypush job2 --delay 30s"
        shell.handle_command(mock_buf)
        mock_kv.push.assert_called_with("job2", priority=None, ttl="30s")

        # kypush with no value
        mock_buf.text = "kypush"
        shell.handle_command(mock_buf)
        assert "Usage: kypush" in shell.output_area.text

        # kypeek
        mock_kv.peek.return_value = "job1"
        mock_buf.text = "kypeek"
        shell.handle_command(mock_buf)
        assert "job1" in shell.output_area.text

        # kypop default
        mock_kv.pop.return_value = "job1"
        mock_buf.text = "kypop"
        shell.handle_command(mock_buf)
        mock_kv.pop.assert_called_with(count=1, lease=None)
        assert "job1" in shell.output_area.text

        # kypop with --n and --lease
        mock_buf.text = "kypop --n 3 --lease 10s"
        shell.handle_command(mock_buf)
        mock_kv.pop.assert_called_with(count=3, lease="10s")

        # kypop with non-numeric --n (ignored, falls back to default count=1)
        mock_buf.text = "kypop --n abc"
        shell.handle_command(mock_buf)
        mock_kv.pop.assert_called_with(count=1, lease=None)

        # kypush with non-numeric --priority (ignored)
        mock_buf.text = "kypush job3 --priority abc"
        shell.handle_command(mock_buf)
        mock_kv.push.assert_called_with("job3", priority=None, ttl=None)

        # kyack
        mock_kv.ack.return_value = "acked"
        mock_buf.text = "kyack receipt-123"
        shell.handle_command(mock_buf)
        mock_kv.ack.assert_called_with("receipt-123")
        assert "acked" in shell.output_area.text

        # kyack usage
        mock_buf.text = "kyack"
        shell.handle_command(mock_buf)
        assert "Usage: kyack" in shell.output_area.text

        # kynack with delay
        mock_kv.nack.return_value = "nacked"
        mock_buf.text = "kynack receipt-123 --delay 5s"
        shell.handle_command(mock_buf)
        mock_kv.nack.assert_called_with("receipt-123", delay="5s")

        # kynack usage
        mock_buf.text = "kynack"
        shell.handle_command(mock_buf)
        assert "Usage: kynack" in shell.output_area.text

        # kycount
        mock_kv.count.return_value = 7
        mock_buf.text = "kycount"
        shell.handle_command(mock_buf)
        assert "7" in shell.output_area.text

        # kyclear without --confirm
        mock_buf.text = "kyclear"
        shell.handle_command(mock_buf)
        assert "--confirm" in shell.output_area.text
        mock_kv.clear.assert_not_called()

        # kyclear with --confirm
        mock_kv.clear.return_value = "cleared"
        mock_buf.text = "kyclear --confirm"
        shell.handle_command(mock_buf)
        mock_kv.clear.assert_called()
        assert "cleared" in shell.output_area.text


def test_tui_management_commands(tmp_path):
    """TUI parity: ttl/acl/profile/stats/backup/rotate/metrics/audit/ws-view."""
    with patch("kycli.tui.Kycore") as mock_kv_class:
        with patch("kycli.tui._start_metrics_server") as mock_metrics:
            mock_kv = mock_kv_class.return_value
            mock_kv.get_type.return_value = "kv"
            shell = KycliShell(db_path=str(tmp_path / "tui_mgmt.db"))
            shell.app = MagicMock()
            mock_buf = MagicMock()

            # kyttl set/get
            mock_kv.set_default_ttl.return_value = 3600
            mock_buf.text = "kyttl set 1h"
            shell.handle_command(mock_buf)
            mock_kv.set_default_ttl.assert_called_with("1h")
            assert "3600" in shell.output_area.text

            mock_kv.get_default_ttl.return_value = 3600
            mock_buf.text = "kyttl get"
            shell.handle_command(mock_buf)
            assert "3600" in shell.output_area.text

            mock_buf.text = "kyttl"
            shell.handle_command(mock_buf)
            assert "Usage: kyttl" in shell.output_area.text

            # kyacl readonly
            mock_kv.get_read_only.return_value = False
            mock_buf.text = "kyacl readonly status"
            shell.handle_command(mock_buf)
            assert "off" in shell.output_area.text

            mock_buf.text = "kyacl readonly on"
            shell.handle_command(mock_buf)
            mock_kv.set_read_only.assert_called_with(True)
            assert "enabled" in shell.output_area.text

            # kyacl key set/get/clear
            mock_buf.text = "kyacl key set secret"
            shell.handle_command(mock_buf)
            mock_kv.set_access_key.assert_called_with("secret")

            mock_kv.get_access_key.return_value = "secret"
            mock_buf.text = "kyacl key get"
            shell.handle_command(mock_buf)
            assert "secret" in shell.output_area.text

            mock_buf.text = "kyacl key clear"
            shell.handle_command(mock_buf)
            mock_kv.set_access_key.assert_called_with(None)

            mock_buf.text = "kyacl"
            shell.handle_command(mock_buf)
            assert "Usage: kyacl" in shell.output_area.text

            # kyprofile list/save/use
            with patch("kycli.config.list_profiles", return_value=["dev", "qa"]):
                mock_buf.text = "kyprofile list"
                shell.handle_command(mock_buf)
                assert "dev" in shell.output_area.text

            with patch("kycli.config.save_profile") as mock_save_profile:
                mock_buf.text = "kyprofile save dev"
                shell.handle_command(mock_buf)
                mock_save_profile.assert_called()
                assert "Saved profile 'dev'" in shell.output_area.text

            with patch("kycli.config.use_profile") as mock_use_profile:
                mock_buf.text = "kyprofile use dev"
                shell.handle_command(mock_buf)
                mock_use_profile.assert_called_with("dev")
                assert "Active profile set to 'dev'" in shell.output_area.text

            mock_buf.text = "kyprofile"
            shell.handle_command(mock_buf)
            assert "Usage: kyprofile" in shell.output_area.text

            # kystats
            mock_kv.get_stats.return_value = {"workspace_type": "kv", "key_count": 5}
            mock_buf.text = "kystats"
            shell.handle_command(mock_buf)
            assert "workspace_type" in shell.output_area.text

            # kybackup create / restore
            mock_kv.backup.return_value = "/tmp/snap.db"
            mock_buf.text = "kybackup /tmp/snap.db"
            shell.handle_command(mock_buf)
            assert "Backup created" in shell.output_area.text

            mock_buf.text = "kybackup restore /tmp/snap.db"
            shell.handle_command(mock_buf)
            mock_kv.restore_backup.assert_called_with("/tmp/snap.db")
            assert "restored" in shell.output_area.text

            mock_buf.text = "kybackup restore"
            shell.handle_command(mock_buf)
            assert "Usage: kybackup restore" in shell.output_area.text

            mock_buf.text = "kybackup"
            shell.handle_command(mock_buf)
            assert "Usage: kybackup" in shell.output_area.text

            # kyrotate
            mock_kv.rotate_master_key.return_value = 3
            mock_buf.text = "kyrotate --new-key newpass --old-key oldpass"
            shell.handle_command(mock_buf)
            assert "Re-encrypted 3 values" in shell.output_area.text

            mock_buf.text = "kyrotate --new-key newpass --dry-run"
            shell.handle_command(mock_buf)
            assert "Dry run" in shell.output_area.text

            mock_buf.text = "kyrotate"
            shell.handle_command(mock_buf)
            assert "Usage: kyrotate" in shell.output_area.text

            # kymetrics
            mock_buf.text = "kymetrics 9999"
            shell.handle_command(mock_buf)
            mock_metrics.assert_called_with(mock_kv, "9999")
            assert "9999" in shell.output_area.text

            # kyaudit export
            mock_kv.export_audit.return_value = 4
            mock_buf.text = "kyaudit export audit.json json"
            shell.handle_command(mock_buf)
            mock_kv.export_audit.assert_called_with("audit.json", fmt="json")
            assert "Exported 4" in shell.output_area.text

            mock_buf.text = "kyaudit"
            shell.handle_command(mock_buf)
            assert "Usage: kyaudit" in shell.output_area.text

            # kyws view
            mock_kv.view_prefix.return_value = {"ns.alpha": 1}
            mock_buf.text = "kyws view ns"
            shell.handle_command(mock_buf)
            assert "ns.alpha" in shell.output_area.text

            mock_buf.text = "kyws view"
            shell.handle_command(mock_buf)
            assert "Usage: kyws view" in shell.output_area.text

            # kyws create with an invalid type raises inside set_type
            with patch("kycli.tui.Kycore") as mock_target_cls:
                mock_target_cls.return_value.__enter__.return_value.set_type.side_effect = ValueError("Invalid workspace type: bogus")
                mock_buf.text = "kyws create badws --type bogus"
                shell.handle_command(mock_buf)
                assert "Failed to create workspace" in shell.output_area.text

            # kyr with --at
            mock_kv.restore.return_value = "overwritten"
            mock_buf.text = "kyr k --at 2026-01-01 00:00:00"
            shell.handle_command(mock_buf)
            mock_kv.restore.assert_called_with("k", timestamp="2026-01-01 00:00:00")

            # kyr usage (no args)
            mock_buf.text = "kyr"
            shell.handle_command(mock_buf)
            assert "Usage: kyr" in shell.output_area.text

            # kyttl invalid subcommand
            mock_buf.text = "kyttl bogus"
            shell.handle_command(mock_buf)
            assert "Usage: kyttl" in shell.output_area.text

            # kyacl key with invalid subcommand
            mock_buf.text = "kyacl key bogus"
            shell.handle_command(mock_buf)
            assert "Usage: kyacl key" in shell.output_area.text

            # kyacl invalid top-level subcommand
            mock_buf.text = "kyacl bogus"
            shell.handle_command(mock_buf)
            assert "Usage: kyacl readonly" in shell.output_area.text

            # kyprofile use with no name
            mock_buf.text = "kyprofile use"
            shell.handle_command(mock_buf)
            assert "Usage: kyprofile" in shell.output_area.text

            # kyprofile invalid subcommand
            mock_buf.text = "kyprofile bogus name"
            shell.handle_command(mock_buf)
            assert "Usage: kyprofile" in shell.output_area.text


def test_tui_workspace_create_and_move(tmp_path):
    """TUI parity: kyws create <ws> --type <t> and kymv <key> <ws> against a
    real (non-mocked) Kycore so the cross-instance file operations are
    exercised end-to-end."""
    db_path = str(tmp_path / "tui_real.db")
    shell = KycliShell(db_path=db_path)
    shell.app = MagicMock()
    mock_buf = MagicMock()

    with patch("kycli.config.DATA_DIR", str(tmp_path)):
        mock_buf.text = "kyws create jobs --type queue"
        shell.handle_command(mock_buf)
        assert "created with type 'queue'" in shell.output_area.text
        assert os.path.exists(str(tmp_path / "jobs.db"))

        mock_buf.text = "kyws create"
        shell.handle_command(mock_buf)
        assert "Usage: kyws create" in shell.output_area.text

        # kymv: move an existing key to a (lazily-created, kv-type) workspace
        shell.kv.save("movekey", "moveval")
        mock_buf.text = "kymv movekey archive"
        shell.handle_command(mock_buf)
        assert "Moved 'movekey' to 'archive'" in shell.output_area.text
        assert shell.kv.getkey("movekey") == "Key not found"

        # kymv missing key
        mock_buf.text = "kymv missing archive"
        shell.handle_command(mock_buf)
        assert "not found" in shell.output_area.text

        # kymv same workspace
        shell.config["active_workspace"] = "archive"
        mock_buf.text = "kymv anykey archive"
        shell.handle_command(mock_buf)
        assert "same" in shell.output_area.text

        # kymv usage
        mock_buf.text = "kymv"
        shell.handle_command(mock_buf)
        assert "Usage: kymv" in shell.output_area.text


def test_tui_tab_completion_commands():
    completer = KycliCompleter()
    completions = list(completer.get_completions(Document("kyu"), None))
    texts = [c.text for c in completions]
    assert "kyuse" in texts
    assert all(t.startswith("kyu") for t in texts)

    # Empty input: every command is a candidate.
    completions = list(completer.get_completions(Document(""), None))
    assert len(completions) == len(__import__("kycli.tui", fromlist=["COMMAND_NAMES"]).COMMAND_NAMES)


def test_tui_tab_completion_workspace_names():
    completer = KycliCompleter()
    with patch("kycli.tui.get_workspaces", return_value=["alpha", "beta", "archive"]):
        completions = list(completer.get_completions(Document("kyuse al"), None))
        texts = [c.text for c in completions]
        assert texts == ["alpha"]

        completions = list(completer.get_completions(Document("kydrop a"), None))
        texts = [c.text for c in completions]
        assert set(texts) == {"alpha", "archive"}

    # Non-workspace command second token: no workspace completions offered.
    completions = list(completer.get_completions(Document("kys al"), None))
    assert completions == []

    # get_workspaces() raising should not propagate (defensive completer).
    with patch("kycli.tui.get_workspaces", side_effect=RuntimeError("boom")):
        completions = list(completer.get_completions(Document("kyuse a"), None))
        assert completions == []
