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

def test_cli_list(clean_home_db, capsys):
    with patch("sys.argv", ["kys", "key1", "val1"]):
        main()
    with patch("sys.argv", ["kyl"]):
        main()
    captured = capsys.readouterr()
    assert "🔑 Keys: key1" in captured.out

def test_cli_delete(clean_home_db, capsys):
    with patch("sys.argv", ["kys", "temp", "val"]):
        main()
    with patch("sys.argv", ["kyd", "temp"]):
        main()
    captured = capsys.readouterr()
    assert "Deleted" in captured.out

def test_cli_validation_error(clean_home_db, capsys):
    with patch("sys.argv", ["kys", "", "val"]):
        main()
    captured = capsys.readouterr()
    assert "⚠️ Validation Error" in captured.out

def test_cli_save_status_messages(clean_home_db, capsys):
    # New key
    with patch("sys.argv", ["kys", "status", "1"]):
        main()
    assert "(New)" in capsys.readouterr().out
    
    # Overwrite - Confirm Yes
    with patch("sys.argv", ["kys", "status", "2"]):
        with patch("builtins.input", return_value="y"):
            main()
    assert "🔄 Updated: status" in capsys.readouterr().out

    # Overwrite - Confirm No
    with patch("sys.argv", ["kys", "status", "3"]):
        with patch("builtins.input", return_value="n"):
            main()
    captured = capsys.readouterr()
    assert "❌ Aborted" in captured.out
    
    # Verify it wasn't changed
    with patch("sys.argv", ["kyg", "status"]):
        main()
    assert "2" in capsys.readouterr().out

    # Identical value
    with patch("sys.argv", ["kys", "status", "2"]):
        main()
    assert "(Value is identical)" in capsys.readouterr().out

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

def test_cli_invalid_command(capsys):
    with patch("sys.argv", ["invalid"]):
        main()
    captured = capsys.readouterr()
    assert "❌ Invalid command" in captured.out

def test_cli_export_import(clean_home_db, capsys, tmp_path):
    # Setup data
    with patch("sys.argv", ["kys", "exp", "val"]):
        main()
    
    export_file = str(tmp_path / "out.csv")
    
    # Export
    with patch("sys.argv", ["kye", export_file]):
        main()
    captured = capsys.readouterr()
    assert "📤 Exported data" in captured.out
    assert os.path.exists(export_file)

    # Import into a different "home"
    other_home = tmp_path / "other_home"
    other_home.mkdir()
    with patch.dict(os.environ, {"HOME": str(other_home)}):
        with patch("sys.argv", ["kyi", export_file]):
            main()
        captured = capsys.readouterr()
        assert "📥 Imported data" in captured.out
        
        with patch("sys.argv", ["kyg", "exp"]):
            main()
        captured = capsys.readouterr()
        assert "val" in captured.out
