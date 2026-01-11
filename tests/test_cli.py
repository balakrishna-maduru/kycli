import pytest
import os
import sys
from unittest.mock import patch, MagicMock
from kycli.cli import main



def test_cli_save_new(clean_home_db, capsys):
    with patch("sys.argv", ["kys", "user", "balu"]):
        main()
    captured = capsys.readouterr()
    assert "Saved: user" in captured.out

def test_cli_save_overwrite(clean_home_db, capsys):
    with patch("sys.argv", ["kys", "user", "balu"]):
        main()
    capsys.readouterr()
    with patch("sys.argv", ["kys", "user", "new_balu"]):
        with patch("builtins.input", return_value="y"):
            main()
    assert "Updated: user" in capsys.readouterr().out

def test_cli_get(clean_home_db, capsys):
    with patch("sys.argv", ["kys", "color", "blue"]):
        main()
    capsys.readouterr()
    with patch("sys.argv", ["kyg", "color"]):
        main()
    assert "blue" in capsys.readouterr().out.strip()

def test_cli_delete_and_restore(clean_home_db, capsys):
    with patch("sys.argv", ["kys", "temp", "val"]):
        main()
    capsys.readouterr()
    with patch("sys.argv", ["kyd", "temp"]):
        with patch("builtins.input", return_value="temp"):
            main()
    assert "Deleted" in capsys.readouterr().out
    with patch("sys.argv", ["kyr", "temp"]):
        main()
    assert "Restored: temp" in capsys.readouterr().out

def test_cli_delete_cancel(clean_home_db, capsys):
    with patch("sys.argv", ["kys", "secure", "locked"]):
        main()
    capsys.readouterr()
    with patch("sys.argv", ["kyd", "secure"]):
        with patch("builtins.input", return_value="wrong"):
            main()
    assert "Confirmation failed" in capsys.readouterr().out

def test_cli_list(clean_home_db, capsys):
    with patch("sys.argv", ["kys", "k1", "v1"]): main()
    with patch("sys.argv", ["kyl"]): main()
    assert "k1" in capsys.readouterr().out

def test_cli_export_import(clean_home_db, tmp_path, capsys):
    export_file = str(tmp_path / "backup.json")
    with patch("sys.argv", ["kys", "exp", "val"]): main()
    capsys.readouterr()
    with patch("sys.argv", ["kye", export_file, "json"]): main()
    assert "Exported data" in capsys.readouterr().out
    other_home = tmp_path / "other"
    other_home.mkdir()
    with patch.dict(os.environ, {"HOME": str(other_home)}):
        with patch("sys.argv", ["kyi", export_file]): main()
        assert "Imported data" in capsys.readouterr().out

def test_cli_json_fail_remains_string(clean_home_db, capsys):
    with patch("sys.argv", ["kys", "bad_json", '{"key": "unclosed_quote}']): main()
    capsys.readouterr()
    with patch("sys.argv", ["kyg", "bad_json"]): main()
    assert '{"key": "unclosed_quote}' in capsys.readouterr().out

def test_cli_save_no_change(clean_home_db, capsys):
    with patch("sys.argv", ["kys", "k", "v"]): main()
    capsys.readouterr()
    with patch("kycli.cli.Kycore") as mock_core:
        mock_core.return_value.__enter__.return_value.getkey.return_value = "v"
        mock_core.return_value.__enter__.return_value.save.return_value = "nochange"
        # Mock containment check
        mock_core.return_value.__enter__.return_value.__contains__.return_value = True
        with patch("sys.argv", ["kys", "k", "v"]): 
            # If we don't mock isatty, it skips prompt (which is fine for this test as value is same)
            # But wait, logic: if key in kv: prompt. Then save. 
            # If we skip prompt, we save. save returns nochange. 
            main()
    assert "✅ No Change: k" in capsys.readouterr().out

def test_cli_kyv_specific_key(clean_home_db, capsys):
    with patch("sys.argv", ["kys", "log", "entry1"]): main()
    capsys.readouterr()
    with patch("sys.argv", ["kyv", "log"]): main()
    assert "entry1" in capsys.readouterr().out

def test_cli_kyg_search_no_match(clean_home_db, capsys):
    with patch("sys.argv", ["kyg", "-s", "nothing_like_this"]): main()
    assert "No matches found" in capsys.readouterr().out

def test_cli_search(clean_home_db, capsys):
    with patch("sys.argv", ["kys", "doc", "hello world"]): main()
    capsys.readouterr()
    with patch("sys.argv", ["kyg", "-s", "hello"]): main()
    assert "doc" in capsys.readouterr().out

def test_cli_import_error(clean_home_db, capsys):
    with patch("sys.argv", ["kyi", "ghost.csv"]): main()
    assert "Error: File not found" in capsys.readouterr().out

def test_cli_usage_errors(clean_home_db, capsys):
    cmds = [["kys", "one"], ["kyg"], ["kyd"], ["kyr"], ["kye"], ["kyi"]]
    for cmd in cmds:
        with patch("sys.argv", cmd): main()
        assert f"Usage: {cmd[0]}" in capsys.readouterr().out

def test_cli_list_no_keys(clean_home_db, capsys):
    with patch("sys.argv", ["kyl"]): main()
    out = capsys.readouterr().out
    assert "no keys found" in out.lower() or "no keys found in workspace" in out.lower()

def test_cli_full_history(clean_home_db, capsys):
    with patch("sys.argv", ["kys", "a", "1"]): main()
    with patch("sys.argv", ["kyv", "-h"]): main()
    assert "Full Audit History" in capsys.readouterr().out

def test_cli_history_empty(clean_home_db, capsys):
    with patch("sys.argv", ["kyv", "missing"]): main()
    assert "No history found" in capsys.readouterr().out

def test_cli_unexpected_error(clean_home_db, capsys):
    with patch("kycli.cli.Kycore", side_effect=Exception("BOOM")):
        with pytest.raises(SystemExit): main()
    assert "Unexpected Error: BOOM" in capsys.readouterr().out

def test_cli_invalid_command_fallback(clean_home_db, capsys):
    with patch("sys.argv", ["unknown_cmd"]): main()
    assert "Invalid command" in capsys.readouterr().out

def test_cli_save_identical(clean_home_db, capsys):
    with patch("sys.argv", ["kys", "same", "val"]): main()
    capsys.readouterr()
    with patch("sys.argv", ["kys", "same", "val"]): main()
    assert "✅ No Change" in capsys.readouterr().out

def test_cli_save_aborted(clean_home_db, capsys):
    with patch("sys.argv", ["kys", "abort", "v1"]): main()
    capsys.readouterr()
    with patch("sys.argv", ["kys", "abort", "v2"]):
        with patch("builtins.input", return_value="n"):
            with patch("sys.stdin.isatty", return_value=True):
                 main()
    assert "Aborted" in capsys.readouterr().out



def test_cli_json_save_and_get(clean_home_db, capsys):
    with patch("sys.argv", ["kys", "user", '{"name": "balu"}']): main()
    capsys.readouterr()
    with patch("sys.argv", ["kyg", "user"]): main()
    assert '"name": "balu"' in capsys.readouterr().out

def test_cli_help(clean_home_db, capsys):
    with patch("sys.argv", ["kyh"]): main()
    assert "Available commands" in capsys.readouterr().out

def test_cli_validation_v_error(clean_home_db, capsys):
    with patch("sys.argv", ["kys", " ", "val"]): main()
    assert "Validation Error" in capsys.readouterr().out

def test_cli_kyv_no_history(clean_home_db, capsys):
    with patch("sys.argv", ["kyv", "non_existent"]):
        main()
    assert "No history found" in capsys.readouterr().out

def test_cli_execute_command(clean_home_db):
    from kycli.cli import main
    # Save a command
    with patch("sys.argv", ["kys", "hi", "echo hello"]):
        main()
    
    # Execute it
    with patch("sys.argv", ["kyc", "hi"]):
        with patch("subprocess.run") as mock_run:
            main()
            mock_run.assert_called()
            # The command should be 'echo hello'
            args, kwargs = mock_run.call_args
            assert args[0] == "echo hello"

def test_cli_execute_dynamic(clean_home_db):
    from kycli.cli import main
    with patch("sys.argv", ["kys", "list", "ls"]):
        main()
    
    with patch("sys.argv", ["kyc", "list", "-la"]):
        with patch("subprocess.run") as mock_run:
            main()
            args, kwargs = mock_run.call_args
            assert args[0] == "ls -la"

def test_cli_execute_error(clean_home_db):
    from kycli.cli import main
    with patch("sys.argv", ["kys", "bad", "exit 1"]):
        main()
    
    with patch("sys.argv", ["kyc", "bad"]):
        import subprocess
        with patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "exit 1")) as mock_run:
            main() # Should catch CalledProcessError
        
        with patch("subprocess.run", side_effect=RuntimeError("fail")) as mock_run:
            main() # Should catch Exception

def test_cli_help_default(clean_home_db):
    from kycli.cli import main
    # Run with empty args and prog name kycli to hit line 40
    with patch("sys.argv", ["kycli"]):
        with patch("kycli.cli.print_help") as mock_help:
            main()
            mock_help.assert_called()


def test_cli_execute_usage_errors(clean_home_db):
    from kycli.cli import main
    # Hit line 178-179
    with patch("sys.argv", ["kyc"]):
        main()
    
    # Hit line 183-184
    with patch("sys.argv", ["kyc", "nonexistent"]):
        main()

def test_cli_restore_to(clean_home_db, capsys):
    from kycli.cli import main
    import time
    from datetime import datetime, timezone
    # Use different keys to avoid confirmation prompt during setup
    with patch("sys.argv", ["kys", "pre_k1", "v1"]): main()
    time.sleep(1.1)
    t1 = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
    time.sleep(1.1)
    with patch("sys.argv", ["kys", "post_k1", "v2"]): main()
    capsys.readouterr()
    
    with patch("sys.argv", ["kyrt", t1]): main()
    assert "Database restored" in capsys.readouterr().out

def test_cli_compact(clean_home_db, capsys):
    from kycli.cli import main
    with patch("sys.argv", ["kyco", "0"]): main()
    assert "Compaction complete" in capsys.readouterr().out

def test_cli_restore_to_usage(clean_home_db, capsys):
    from kycli.cli import main
    with patch("sys.argv", ["kyrt"]): 
        main()
    assert "Usage: kyrt" in capsys.readouterr().out


def test_cli_advanced_ops(clean_home_db, capsys):
    from kycli.cli import main
    
    # Test kypush
    with patch("sys.argv", ["kypush", "list", "item1"]): main()
    assert "created" in capsys.readouterr().out
    
    # Test kypush --unique
    with patch("sys.argv", ["kypush", "list", "item1", "--unique"]): main()
    assert "nochange" in capsys.readouterr().out
    
    # Test kyrem
    with patch("sys.argv", ["kyrem", "list", "item1"]): main()
    assert "overwritten" in capsys.readouterr().out
    
    # Test kyfo
    with patch("sys.argv", ["kyfo"]): main()
    assert "optimized" in capsys.readouterr().out

    # Test kyg regex results
    with patch("sys.argv", ["kys", "user_1", "v1"]): main()
    with patch("sys.argv", ["kys", "user_2", "v2"]): main()
    capsys.readouterr()
    with patch("sys.argv", ["kyg", "user_.*"]): main()
    out = capsys.readouterr().out
    assert "user_1" in out
    assert "user_2" in out

def test_cli_patching(clean_home_db, capsys):
    from kycli.cli import main
    # Initial save
    with patch("sys.argv", ["kys", "user", '{"profile": {"name": "balu"}}']): main()
    capsys.readouterr()
    
    # Patch via kys with dot
    with patch("sys.argv", ["kys", "user.profile.name", "maduru"]):
        with patch("builtins.input", return_value="y"):
            main()
    assert "Updated" in capsys.readouterr().out or "Saved" in capsys.readouterr().out or "Patched" in capsys.readouterr().out
    
    # Verify
    with patch("sys.argv", ["kyg", "user.profile.name"]): main()
    assert "maduru" in capsys.readouterr().out

def test_cli_argument_combinations(clean_home_db, capsys):
    from kycli.cli import main
    with patch("sys.argv", ["kys", "k1_comb", "v1_comb"]): main()
    capsys.readouterr()
    
    # kyf with --limit and --keys-only (use kyg -s now)
    with patch("sys.argv", ["kyg", "v1_comb", "--limit", "1", "--keys-only", "-s"]): main()
    out = capsys.readouterr().out
    assert "k1_comb" in out
    assert "v1_comb" not in out
    
    # kyg with --key (master key)
    with patch("sys.argv", ["kys", "secret", "data", "--key", "pass"]): main()
    capsys.readouterr()
    with patch("sys.argv", ["kyg", "secret", "--key", "pass"]): main()
    assert "data" in capsys.readouterr().out

def test_main_coverage(clean_home_db):
    from kycli.cli import main
    # To hit the if __name__ == "__main__": main()
    # we can't easily do it via import, but we can call main()
    # which we already do.
    pass

def test_cli_argument_parsing_edge_cases(clean_home_db, capsys):
    # Hit skip_next logic (line 106-113)
    # kys key val --key k --ttl 1s
    with patch("sys.argv", ["kys", "k1", "v1", "--key", "pass", "--ttl", "10s"]):
        main()
    capsys.readouterr()
    
    # Hit --limit parsing failure (line 118-119)
    # Use kyg -s to trigger limit usage
    # Parsing failure might exit or ignore. Code: except: pass.
    # But let's be safe.
    try:
        with patch("sys.argv", ["kyg", "query", "--limit", "not_int", "-s"]):
            main()
    except SystemExit: pass
    capsys.readouterr()
    
    with pytest.raises(SystemExit):
        with patch("sys.argv", ["kyg", "query", "--keys-only", "-s"]):
            main()
    capsys.readouterr()

def test_cli_save_status_nochange_mocked(clean_home_db):
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


def test_cli_kyg_search_success(clean_home_db, capsys):
    # Setup data
    with patch("sys.argv", ["kys", "user.1", '{"name": "balu", "role": "admin"}']): main()
    with patch("sys.argv", ["kys", "user.2", '{"name": "test", "role": "dev"}']): main()
    capsys.readouterr()

    # Search for 'admin'
    with patch("sys.argv", ["kyg", "-s", "admin"]): main()
    output = capsys.readouterr().out
    assert "user.1" in output
    assert "balu" in output
    assert "user.2" not in output

def test_cli_kyg_search_keys_only(clean_home_db, capsys):
    with patch("sys.argv", ["kys", "prod_db", "secret"]): main()
    capsys.readouterr()
    
    with patch("sys.argv", ["kyg", "-s", "secret", "--keys-only"]): main()
    output = capsys.readouterr().out
    assert "Found 1 keys" in output
    assert "prod_db" in output

def test_cli_kyg_search_no_match(clean_home_db, capsys):
    with patch("sys.argv", ["kyg", "-s", "nonexistent"]): main()
    assert "No matches found" in capsys.readouterr().out

def test_cli_patch_success(clean_home_db, capsys):
    with patch("sys.argv", ["kys", "user", '{"age": 20}']): main()
    capsys.readouterr()
    with patch("sys.argv", ["kypatch", "user.age", "25"]): main()
    assert "Patched: user.age" in capsys.readouterr().out
    with patch("sys.argv", ["kyg", "user.age"]): main()
    assert "25" in capsys.readouterr().out

def test_cli_patch_usage(clean_home_db, capsys):
    with patch("sys.argv", ["kypatch"]): main()
    assert "Usage: kypatch" in capsys.readouterr().out

def test_cli_push_usage(clean_home_db, capsys):
    with patch("sys.argv", ["kypush"]): main()
    assert "Usage: kypush" in capsys.readouterr().out

def test_cli_remove_usage(clean_home_db, capsys):
    with patch("sys.argv", ["kyrem"]): main()
    assert "Usage: kyrem" in capsys.readouterr().out

def test_cli_restore_at(clean_home_db, capsys):
    import time
    from datetime import datetime, timezone
    with patch("sys.argv", ["kys", "k", "v1"]): main()
    time.sleep(1.5)
    # Use UTC to match SQLite CURRENT_TIMESTAMP
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    time.sleep(1.5)
    with patch("sys.argv", ["kys", "k", "v2"]): main()
    capsys.readouterr()
    
    with patch("sys.argv", ["kyrt", "k", "--at", ts]): main()
    output = capsys.readouterr().out
    assert "overwritten" in output

def test_cli_patch_types_and_error(clean_home_db, capsys):
    with patch("sys.argv", ["kys", "obj", '{"a": 1}']): main()
    capsys.readouterr()
    
    # Test True
    with patch("sys.argv", ["kypatch", "obj.a", "true"]): main()
    assert "Patched" in capsys.readouterr().out
    
def test_cli_patch_error(clean_home_db, capsys):
    # Mock kv.patch to return error to test CLI path
    with patch("kycli.cli.Kycore") as mock_core:
        mock_core.return_value.__enter__.return_value.patch.return_value = "Error: Cannot patch"
        with patch("sys.argv", ["kypatch", "k", "v"]): main()
    assert "❌ Error: Cannot patch" in capsys.readouterr().out

def test_cli_kyc_failure(clean_home_db, capsys):
    import subprocess
    with patch("sys.argv", ["kys", "fail_cmd", "exit 1"]): main()
    
    with patch("sys.argv", ["kyc", "fail_cmd"]): 
        # We need to ensure subprocess.run actually runs and fails
        # Using real subprocess might be unsafe or flaky.
        # Better to mock subprocess.run to raise CalledProcessError
        with patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "exit 1")):
            main()
    assert "failed with exit code 1" in capsys.readouterr().out

# --- Gap Coverage Tests ---

def test_cli_move_exception(capsys):
    from kycli.cli import main
    try:
        from unittest.mock import patch
    except ImportError: pass
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
    try:
        from unittest.mock import patch
    except ImportError: pass
    with patch("sys.argv", ["kyc", "key"]):
         with patch("kycli.cli.Kycore") as mock_kv:
            inst = mock_kv.return_value
            inst.__enter__.return_value = inst
            inst.getkey.return_value = "ls"
            
            with patch("subprocess.run", side_effect=Exception("Exec failed")):
                main()
                assert "Execution Error" in capsys.readouterr().out

def test_cli_kyws_current(capsys):
    from kycli import cli
    try:
        from unittest.mock import patch
    except ImportError: pass
    with patch("sys.argv", ["kycli", "kyws", "--current"]), \
         patch("kycli.cli.load_config", return_value={"active_workspace": "testbox", "db_path": ":memory:", "export_format": "csv"}):
         cli.main()
    out, _ = capsys.readouterr()
    assert "testbox" in out

def test_cli_kyws_args(capsys):
    from kycli import cli
    try:
        from unittest.mock import patch
    except ImportError: pass
    with patch("sys.argv", ["kycli", "kyws", "arg1"]), \
         patch("kycli.cli.load_config", return_value={"active_workspace": "default", "db_path": ":memory:"}):
         cli.main()
    # Should print error or ignore
    # The actual implementation prints available workspaces.
    pass

def test_kydrop_exception(capsys):
    from kycli.cli import main
    try:
        from unittest.mock import patch, mock_open
    except ImportError: pass
    with patch("sys.argv", ["kydrop", "ws_err"]), \
         patch("kycli.config.DATA_DIR", "/tmp"), \
         patch("os.path.exists", return_value=True), \
         patch("builtins.input", return_value="y"), \
         patch("os.remove", side_effect=OSError("Disk error")):
        main()
    assert "Error deleting workspace" in capsys.readouterr().out

def test_init_already_initialized(capsys):
    from kycli.cli import main
    try:
        from unittest.mock import patch, mock_open
    except ImportError: pass
    mock_file = mock_open(read_data="# >>> kycli initialize >>>")
    with patch("sys.argv", ["init"]), \
         patch("os.environ.get", return_value="/bin/zsh"), \
         patch("os.path.expanduser", return_value="/tmp"), \
         patch("os.path.exists", return_value=True), \
         patch("builtins.open", mock_file):
        main()
    assert "Already initialized" in capsys.readouterr().out

def test_init_write_error(capsys):
    from kycli.cli import main
    try:
        from unittest.mock import patch, mock_open
    except ImportError: pass
    mock_file = mock_open(read_data="")
    mock_file.side_effect = OSError("Write failed")
    
    def side_effect(file, mode="r", *args, **kwargs):
        if "a" in mode:
             raise OSError("Write failed")
        return mock_open(read_data="")(file, mode, *args, **kwargs)

    with patch("sys.argv", ["init"]), \
         patch("os.environ.get", return_value="/bin/zsh"), \
         patch("os.path.expanduser", return_value="/tmp"), \
         patch("os.path.exists", return_value=False), \
         patch("builtins.open", side_effect=side_effect):
        main()
    assert "Error writing" in capsys.readouterr().out
