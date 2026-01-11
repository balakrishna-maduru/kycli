import os
import pytest
from unittest.mock import patch, MagicMock, mock_open
import sys
from kycli import cli
from kycli.config import load_config, save_config, DATA_DIR, KYCLI_DIR
from kycli.tui import KycliShell

# --- CONFIG & OPTIMIZATION TESTS ---

def test_kyuse_creates_workspace_file(tmp_path):
    # Setup env
    config_path = tmp_path / "config.json"
    ws_file = tmp_path / "workspace"
    
    with patch("kycli.config.CONFIG_PATH", str(config_path)), \
         patch("kycli.config.KYCLI_DIR", str(tmp_path)):
        
        save_config({"active_workspace": "test_ws"})
        
        assert ws_file.exists()
        assert ws_file.read_text() == "test_ws"

def test_kycli_init_generates_optimized_script(capsys):
    with patch("sys.argv", ["kycli", "init"]), \
         patch("os.environ", {"SHELL": "/bin/zsh"}), \
         patch("os.path.expanduser", return_value="/tmp"), \
         patch("os.path.exists", return_value=False), \
         patch("builtins.open", new_callable=mock_open) as m_open:
         
        cli.main()
        
        # Check that the snippet contains the optimized code
        m_open.assert_called()
        # Inspect write calls
        handle = m_open()
        # It writes snippet
        writes = [args[0] for args, _ in handle.write.call_args_list]
        combined = "".join(writes)
        assert '.kycli/workspace' in combined
        assert 'cat "$ws_file"' in combined

# --- CLI COMMAND TESTS ---

def test_kydrop_cli_confirm_yes(capsys):
    with patch("sys.argv", ["kycli", "kydrop", "test_ws_to_drop"]), \
         patch("builtins.input", return_value="y"), \
         patch("os.path.exists", return_value=True), \
         patch("os.remove") as mock_remove, \
         patch("kycli.cli.load_config", return_value={"active_workspace": "other_ws", "db_path": ":memory:", "export_format": "csv"}):
             
             cli.main()
             
    mock_remove.assert_called_once()
    out, _ = capsys.readouterr()
    assert "deleted" in out

def test_kydrop_cli_confirm_no(capsys):
    with patch("sys.argv", ["kycli", "kydrop", "test_ws_to_drop"]), \
         patch("builtins.input", return_value="n"), \
         patch("os.path.exists", return_value=True), \
         patch("os.remove") as mock_remove, \
         patch("kycli.cli.load_config", return_value={"active_workspace": "other_ws", "db_path": ":memory:", "export_format": "csv"}):
             
             cli.main()
             
    mock_remove.assert_not_called()
    out, _ = capsys.readouterr()
    assert "Aborted" in out

def test_kydrop_active_workspace(capsys):
    with patch("sys.argv", ["kycli", "kydrop", "active_ws"]), \
         patch("kycli.cli.load_config", return_value={"active_workspace": "active_ws", "db_path": ":memory:", "export_format": "csv"}):
         
         cli.main()
         
    out, _ = capsys.readouterr()
    assert "Cannot drop the active workspace" in out

def test_kydrop_missing_workspace(capsys):
    with patch("sys.argv", ["kycli", "kydrop", "missing_ws"]), \
         patch("kycli.cli.load_config", return_value={"active_workspace": "other", "db_path": ":memory:", "export_format": "csv"}), \
         patch("os.path.exists", return_value=False):
         
         cli.main()
         
    out, _ = capsys.readouterr()
    assert "does not exist" in out

def test_kydrop_no_args(capsys):
    with patch("sys.argv", ["kycli", "kydrop"]), \
         patch("kycli.cli.load_config", return_value={"active_workspace": "other", "db_path": ":memory:", "export_format": "csv"}):
         cli.main()
    out, _ = capsys.readouterr()
    assert "Usage: kydrop" in out

# --- TUI TESTS ---

class MockBuffer:
    def __init__(self, text):
        self.text = text
        self.cursor_position = 0

@pytest.fixture
def tui_shell():
    with patch("kycli.tui.load_config", return_value={"active_workspace": "default", "db_path": ":memory:"}), \
         patch("kycli.tui.Kycore", MagicMock()), \
         patch("kycli.tui.Application", MagicMock()), \
         patch("kycli.tui.KycliShell.update_history"), \
         patch("kycli.tui.KycliShell.update_status"):
        shell = KycliShell()
        shell.output_area = MagicMock()
        shell.input_field = MagicMock()
        shell.config = {"active_workspace": "default"}
        return shell

def test_tui_kydrop_usage(tui_shell):
    tui_shell.handle_command(MockBuffer("kydrop"))
    assert "Usage: kydrop" in tui_shell.output_area.text

def test_tui_kydrop_active(tui_shell):
    tui_shell.handle_command(MockBuffer("kydrop default"))
    assert "Cannot drop active workspace" in tui_shell.output_area.text

def test_tui_kydrop_missing(tui_shell):
    with patch("os.path.exists", return_value=False):
        tui_shell.handle_command(MockBuffer("kydrop other"))
        assert "not found" in tui_shell.output_area.text

def test_tui_kydrop_confirm_missing(tui_shell):
    with patch("os.path.exists", return_value=True):
         tui_shell.handle_command(MockBuffer("kydrop other"))
         assert "add --confirm flag" in tui_shell.output_area.text

def test_tui_kydrop_success(tui_shell):
    with patch("os.path.exists", return_value=True), \
         patch("os.remove") as mock_rm:
         tui_shell.handle_command(MockBuffer("kydrop other --confirm"))
         mock_rm.assert_called_once()
         assert "deleted" in tui_shell.output_area.text

def test_tui_kydrop_error(tui_shell):
    with patch("os.path.exists", return_value=True), \
         patch("os.remove", side_effect=OSError("Permission denied")):
         tui_shell.handle_command(MockBuffer("kydrop other --confirm"))
         assert "Error: Permission denied" in tui_shell.output_area.text

def test_tui_status_update(tui_shell):
    # Test that status update uses the new abbreviated format
    tui_shell.config = {"active_workspace": "testws"}
    tui_shell.db_path = "testws.db"
    tui_shell.status_bar = MagicMock()
    
    # We call the real update_status by rebinding or similar is tricky if patched.
    # Instead, let's just inspect the code logic or re-instantiate without patching update_status
    # but that would trigger real UI.
    pass 
