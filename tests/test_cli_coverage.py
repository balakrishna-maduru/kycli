import pytest
from unittest.mock import patch, mock_open, MagicMock
from kycli.cli import main
import os

def test_kydrop_exception(capsys):
    with patch("sys.argv", ["kydrop", "ws_err"]), \
         patch("kycli.config.DATA_DIR", "/tmp"), \
         patch("os.path.exists", return_value=True), \
         patch("builtins.input", return_value="y"), \
         patch("os.remove", side_effect=OSError("Disk error")):
        main()
    assert "Error deleting workspace" in capsys.readouterr().out

def test_init_already_initialized(capsys):
    mock_file = mock_open(read_data="# >>> kycli initialize >>>")
    with patch("sys.argv", ["init"]), \
         patch("os.environ.get", return_value="/bin/zsh"), \
         patch("os.path.expanduser", return_value="/tmp"), \
         patch("os.path.exists", return_value=True), \
         patch("builtins.open", mock_file):
        main()
    assert "Already initialized" in capsys.readouterr().out

def test_init_write_error(capsys):
    mock_file = mock_open(read_data="")
    mock_file.side_effect = OSError("Write failed")
    # Need to fail on open for writing (append)
    # mock_open handles read.
    # To fail on 'a' open:
    
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
