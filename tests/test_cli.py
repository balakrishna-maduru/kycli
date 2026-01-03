import pytest
import os
import sys
from unittest.mock import patch, MagicMock
from kycli.cli import main

@pytest.fixture
def clean_home_db(tmp_path, monkeypatch):
    """Ensure a clean home directory and DB for each test."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr("os.path.expanduser", lambda x: str(fake_home / "kydata.db") if x == "~/kydata.db" else x)
    monkeypatch.setenv("HOME", str(fake_home))
    return fake_home

def test_cli_save_new(clean_home_db, capsys):
    with patch("sys.argv", ["kys", "user", "balu"]):
        main()
    captured = capsys.readouterr()
    assert "Saved: user (New)" in captured.out

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
    assert "Deleted and moved to archive" in capsys.readouterr().out
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
        with patch("sys.argv", ["kys", "k", "v"]): main()
    assert "➖ No change: k" in capsys.readouterr().out

def test_cli_kyv_specific_key(clean_home_db, capsys):
    with patch("sys.argv", ["kys", "log", "entry1"]): main()
    capsys.readouterr()
    with patch("sys.argv", ["kyv", "log"]): main()
    assert "entry1" in capsys.readouterr().out

def test_cli_kyf_no_match(clean_home_db, capsys):
    with patch("sys.argv", ["kyf", "nothing_like_this"]): main()
    assert "No matches found" in capsys.readouterr().out

def test_cli_kyf_usage(clean_home_db, capsys):
    with patch("sys.argv", ["kyf"]): main()
    assert "Usage: kyf" in capsys.readouterr().out

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
    assert "No keys found" in capsys.readouterr().out

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
    assert "Value is identical" in capsys.readouterr().out

def test_cli_save_aborted(clean_home_db, capsys):
    with patch("sys.argv", ["kys", "abort", "v1"]): main()
    capsys.readouterr()
    with patch("sys.argv", ["kys", "abort", "v2"]):
        with patch("builtins.input", return_value="n"): main()
    assert "Aborted" in capsys.readouterr().out

def test_cli_search(clean_home_db, capsys):
    with patch("sys.argv", ["kys", "doc", "hello world"]): main()
    capsys.readouterr()
    with patch("sys.argv", ["kyf", "hello"]): main()
    assert "doc" in capsys.readouterr().out

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
