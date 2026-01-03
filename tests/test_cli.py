import sys
import os
from unittest.mock import patch
from io import StringIO
from kycli.cli import main
import pytest

@pytest.fixture
def clean_home_db(tmp_path, monkeypatch):
    """Mock home directory to avoid touching real ~/kydata.db"""
    fake_home = tmp_path / "fake_home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    return fake_home

def test_cli_help(capsys):
    with patch("sys.argv", ["kyh"]):
        main()
    captured = capsys.readouterr()
    assert "Available commands" in captured.out

def test_cli_save_and_get(clean_home_db, capsys):
    # Test Save
    with patch("sys.argv", ["kys", "name", "balu"]):
        main()
    captured = capsys.readouterr()
    assert "✅ Saved: name" in captured.out

    # Test Get
    with patch("sys.argv", ["kyg", "name"]):
        main()
    captured = capsys.readouterr()
    assert "balu" in captured.out

def test_cli_delete_and_restore(clean_home_db, capsys):
    # Setup
    with patch("sys.argv", ["kys", "secret", "top_secret"]):
        main()
    capsys.readouterr()

    # Delete with confirmation
    with patch("sys.argv", ["kyd", "secret"]):
        with patch("builtins.input", return_value="secret"):
            main()
    
    captured = capsys.readouterr()
    assert "Deleted" in captured.out
    
    # Verify it's gone
    with patch("sys.argv", ["kyg", "secret"]):
        main()
    assert "Key not found" in capsys.readouterr().out

    # Restore
    with patch("sys.argv", ["kyr", "secret"]):
        main()
    
    captured = capsys.readouterr()
    assert "Restored: secret" in captured.out
    
    # Verify it's back
    with patch("sys.argv", ["kyg", "secret"]):
        main()
    assert "top_secret" in capsys.readouterr().out

def test_cli_delete_cancel(clean_home_db, capsys):
    with patch("sys.argv", ["kys", "stay", "here"]): main()
    capsys.readouterr()

    # Delete with WRONG confirmation
    with patch("sys.argv", ["kyd", "stay"]):
        with patch("builtins.input", return_value="wrong"):
            main()
    
    assert "Aborted" in capsys.readouterr().out
    
    # Verify it's still there
    with patch("sys.argv", ["kyg", "stay"]): main()
    assert "here" in capsys.readouterr().out

def test_cli_validation_error(clean_home_db, capsys):
    with patch("sys.argv", ["kys", "", "val"]):
        main()
    captured = capsys.readouterr()
    assert "⚠️ Validation Error" in captured.out

def test_cli_history(clean_home_db, capsys):
    with patch("sys.argv", ["kys", "h", "1"]): main()
    with patch("sys.argv", ["kys", "h", "2"]): 
        with patch("builtins.input", return_value="y"):
            main()
    
    # Clear setup output
    capsys.readouterr()

    with patch("sys.argv", ["kyv", "h"]):
        main()
    captured = capsys.readouterr()
    assert captured.out.strip() == "2"

def test_cli_export_import(clean_home_db, capsys, tmp_path):
    # Setup data
    with patch("sys.argv", ["kys", "exp", "val"]):
        main()
    
    export_file = str(tmp_path / "out.csv")
    
    # Export
    with patch("sys.argv", ["kye", export_file]):
        main()
    capsys.readouterr()

    # Import into a different "home"
    other_home = tmp_path / "other_home"
    other_home.mkdir()
    # We need to monkeypatch HOME for the new process logic if we weren't using context manager
    # but here Kycore() uses os.path.expanduser
    with patch.dict(os.environ, {"HOME": str(other_home)}):
        with patch("sys.argv", ["kyi", export_file]):
            main()
        
        with patch("sys.argv", ["kyg", "exp"]):
            main()
        captured = capsys.readouterr()
        assert "val" in captured.out

def test_cli_usage_errors(clean_home_db, capsys):
    # kys wrong args
    with patch("sys.argv", ["kys", "one"]):
        main()
    assert "Usage: kys" in capsys.readouterr().out
    
    # kyg wrong args
    with patch("sys.argv", ["kyg"]):
        main()
    assert "Usage: kyg" in capsys.readouterr().out
    
    # kyd wrong args
    with patch("sys.argv", ["kyd"]):
        main()
    assert "Usage: kyd" in capsys.readouterr().out

    # kyr wrong args
    with patch("sys.argv", ["kyr"]):
        main()
    assert "Usage: kyr" in capsys.readouterr().out

    # kye wrong args
    with patch("sys.argv", ["kye"]):
        main()
    assert "Usage: kye" in capsys.readouterr().out

    # kyi wrong args
    with patch("sys.argv", ["kyi"]):
        main()
    assert "Usage: kyi" in capsys.readouterr().out

def test_cli_list_no_keys(clean_home_db, capsys):
    with patch("sys.argv", ["kyl"]):
        main()
    assert "No keys found" in capsys.readouterr().out

def test_cli_full_history(clean_home_db, capsys):
    with patch("sys.argv", ["kys", "a", "1"]): main()
    with patch("sys.argv", ["kyv", "-h"]):
        main()
    out = capsys.readouterr().out
    assert "Full Audit History" in out
    assert "a" in out

def test_cli_history_empty(clean_home_db, capsys):
    with patch("sys.argv", ["kyv", "missing"]):
        main()
    assert "No history found" in capsys.readouterr().out

def test_cli_unexpected_error(clean_home_db, capsys):
    # Mock Kycore to raise a generic exception
    with patch("kycli.cli.Kycore", side_effect=Exception("BOOM")):
        with pytest.raises(SystemExit):
            main()
    assert "Unexpected Error: BOOM" in capsys.readouterr().out

def test_cli_invalid_command_fallback(clean_home_db, capsys):
    with patch("sys.argv", ["unknown_cmd"]):
        main()
    out = capsys.readouterr().out
    assert "Invalid command" in out
    assert "Available commands" in out

def test_cli_save_identical(clean_home_db, capsys):
    with patch("sys.argv", ["kys", "same", "val"]): main()
    capsys.readouterr()
    with patch("sys.argv", ["kys", "same", "val"]):
        main()
    assert "Value is identical" in capsys.readouterr().out

def test_cli_save_aborted(clean_home_db, capsys):
    with patch("sys.argv", ["kys", "abort", "v1"]): main()
    capsys.readouterr()
    with patch("sys.argv", ["kys", "abort", "v2"]):
        with patch("builtins.input", return_value="n"):
            main()
    assert "Aborted" in capsys.readouterr().out

def test_cli_import_not_found(clean_home_db, capsys):
    with patch("sys.argv", ["kyi", "nonexistent.csv"]):
        main()
    assert "Error: File not found" in capsys.readouterr().out
