import http.client
import json
import logging
import os
from unittest.mock import patch

import pytest

from kycli import config as config_module
from kycli.cli import _render_value, _start_metrics_server, main
from kycli.logging_utils import get_logger
from kycli.utils import coerce_value


class _StatsStub:
    def get_stats(self):
        return {"ok": True}


def test_render_value_and_metrics_server():
    assert _render_value({"a": 1}, as_json=True).startswith("{")
    assert _render_value({"a": 1}, pretty=True).startswith("{")
    assert _render_value(["a", "b"], pretty=True) == "a\nb"
    assert _render_value(["a", "b"]).startswith("[")
    assert _render_value(10) == "10"

    server = _start_metrics_server(_StatsStub(), 0)
    port = server.server_address[1]
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
    conn.request("GET", "/")
    response = conn.getresponse()
    assert response.status == 200
    assert json.loads(response.read().decode("utf-8"))["ok"] is True
    conn.close()

    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
    conn.request("GET", "/missing")
    response = conn.getresponse()
    assert response.status == 404
    conn.close()
    server.shutdown()
    server.server_close()


def test_logging_utils_and_utils_branches(tmp_path, monkeypatch):
    monkeypatch.setattr("kycli.logging_utils.KYCLI_DIR", str(tmp_path))
    monkeypatch.setenv("KYCLI_LOG_PATH", str(tmp_path / "kycli.log"))
    monkeypatch.setenv("KYCLI_LOG_LEVEL", "DEBUG")

    logger = get_logger("gap.logger")
    assert logger.level == logging.DEBUG
    assert get_logger("gap.logger") is logger

    assert coerce_value(5) == 5
    assert coerce_value('"x"', json_mode="invalid-mode") == '"x"'
    assert coerce_value('{"a":1}', json_mode="never") == '{"a":1}'


def test_config_profile_gap_branches():
    assert config_module._apply_active_profile({"active_profile": None, "profiles": {}})["profiles"] == {}
    assert config_module._apply_active_profile({"active_profile": "missing", "profiles": {}})["active_profile"] == "missing"
    assert config_module._apply_active_profile({"active_profile": "bad", "profiles": {"bad": "x"}})["active_profile"] == "bad"

    with pytest.raises(ValueError):
        config_module.save_profile("", {})
    with pytest.raises(ValueError):
        config_module.use_profile("missing")


def test_cli_gap_branches(clean_home_db, tmp_path, capsys):
    with patch("sys.argv", ["kyprofile"]):
        main()
    assert "Usage: kyprofile" in capsys.readouterr().out

    with patch("sys.argv", ["kyprofile", "save"]):
        main()
    assert "Usage: kyprofile" in capsys.readouterr().out

    with patch("sys.argv", ["kyprofile", "bogus", "name"]):
        main()
    assert "Usage: kyprofile" in capsys.readouterr().out

    with patch("sys.argv", ["kyprofile", "use", "missing"]):
        main()
    assert "Validation Error" in capsys.readouterr().out

    with patch("sys.argv", ["kyws", "view"]):
        main()
    assert "Usage: kyws view <prefix>" in capsys.readouterr().out

    with patch("sys.argv", ["kyttl"]):
        main()
    assert "Usage: kyttl" in capsys.readouterr().out

    with patch("sys.argv", ["kyttl", "set"]):
        main()
    assert "Usage: kyttl" in capsys.readouterr().out

    with patch("sys.argv", ["kyacl"]):
        main()
    assert "Usage: kyacl" in capsys.readouterr().out

    with patch("sys.argv", ["kyacl", "key"]):
        main()
    assert "Usage: kyacl key" in capsys.readouterr().out

    with patch("sys.argv", ["kyacl", "key", "get"]):
        main()
    assert capsys.readouterr().out == "\n"

    with patch("sys.argv", ["kyacl", "key", "clear"]):
        main()
    assert "Access key cleared" in capsys.readouterr().out

    with patch("sys.argv", ["kyacl", "bogus"]):
        main()
    assert "Usage: kyacl" in capsys.readouterr().out

    with patch("sys.argv", ["kyws", "create"]):
        main()
    assert "Usage: kyws create" in capsys.readouterr().out

    with patch("sys.argv", ["kyws", "create", "q2", "--type", "queue"]):
        main()
    capsys.readouterr()
    with patch("sys.argv", ["kyuse", "q2"]):
        main()
    capsys.readouterr()
    with patch("sys.argv", ["kypush", "--file"]):
        main()
    assert "Usage: kypush --file <path>" in capsys.readouterr().out

    with patch("sys.argv", ["kypush", "--file", str(tmp_path / "missing.txt")]):
        main()
    assert "File not found" in capsys.readouterr().out

    with patch("sys.argv", ["kyack"]):
        main()
    assert "Usage: kyack <receipt_id>" in capsys.readouterr().out

    with patch("sys.argv", ["kynack"]):
        main()
    assert "Usage: kynack <receipt_id>" in capsys.readouterr().out

    with patch("sys.argv", ["kyuse", "default"]):
        main()
    capsys.readouterr()

    with patch("sys.argv", ["kyv", "export"]):
        main()
    assert "Usage: kyv export <file> [format]" in capsys.readouterr().out

    with patch("sys.argv", ["kys", "h1", "v1"]):
        main()
    capsys.readouterr()
    with patch("sys.argv", ["kyv", "-h", "--json"]):
        main()
    assert json.loads(capsys.readouterr().out)[0]["key"] == "h1"

    with patch("sys.argv", ["kybackup"]):
        main()
    assert "Usage: kybackup <file> OR kybackup restore <file>" in capsys.readouterr().out

    with patch("sys.argv", ["kybackup", "restore"]):
        main()
    assert "Usage: kybackup restore <file>" in capsys.readouterr().out

    with patch("kycli.cli._start_metrics_server") as mock_metrics:
        with patch("sys.argv", ["kymetrics"]):
            main()
        assert mock_metrics.called
        assert "Metrics endpoint started" in capsys.readouterr().out

    with patch("sys.argv", ["kyaudit"]):
        main()
    assert "Usage: kyaudit export <file> [format]" in capsys.readouterr().out


def test_cli_arg_parsing_gap_branches(clean_home_db, capsys):
    with patch("sys.argv", ["kycli", "kys", "num", "value", "--priority", "bad", "--batch", "bad", "--limit", "bad", "--json", "--pretty"]):
        main()
    out = capsys.readouterr().out
    assert "Saved: num" in out or "Updated: num" in out

    with patch("sys.argv", ["kycli", "kyh", "--delay", "1s", "--lease", "2s", "--n", "3", "--access-key", "k", "--since", "2026-01-01", "--until", "2026-12-31"]):
        main()
    assert "Available commands" in capsys.readouterr().out


def test_cli_remaining_roadmap_success_branches(clean_home_db, tmp_path, capsys):
    audit_file = tmp_path / "audit.csv"
    backup_file = tmp_path / "snap.db"

    with patch("sys.argv", ["kyacl", "readonly", "off"]):
        main()
    assert "Read-only disabled" in capsys.readouterr().out

    with patch("sys.argv", ["kyacl", "key", "set", "abc123"]):
        main()
    assert "Access key set" in capsys.readouterr().out

    with patch.dict(os.environ, {"KYCLI_ACCESS_KEY": "abc123"}):
        with patch("sys.argv", ["kys", "hist", "value1"]):
            main()
    capsys.readouterr()
    with patch.dict(os.environ, {"KYCLI_ACCESS_KEY": "abc123"}):
        with patch("sys.argv", ["kyv", "export", str(audit_file), "csv"]):
            main()
    assert "Exported" in capsys.readouterr().out
    assert audit_file.exists()

    with patch("sys.argv", ["kyws", "create", "q3", "--type", "queue"]):
        main()
    capsys.readouterr()
    with patch("sys.argv", ["kyuse", "q3"]):
        main()
    capsys.readouterr()
    with patch("sys.argv", ["kypush", "jobx"]):
        main()
    capsys.readouterr()
    with patch("sys.argv", ["kypop", "--lease", "10s", "--json"]):
        main()
    lease_data = json.loads(capsys.readouterr().out)
    with patch("sys.argv", ["kyack", lease_data["receipt_id"]]):
        main()
    assert "acked" in capsys.readouterr().out

    with patch("sys.argv", ["kyuse", "default"]):
        main()
    capsys.readouterr()
    with patch.dict(os.environ, {"KYCLI_ACCESS_KEY": "abc123"}):
        with patch("sys.argv", ["kybackup", str(backup_file)]):
            main()
    capsys.readouterr()
    with patch.dict(os.environ, {"KYCLI_ACCESS_KEY": "abc123"}):
        with patch("sys.argv", ["kys", "restoreme", "changed"]):
            main()
    capsys.readouterr()
    with patch.dict(os.environ, {"KYCLI_ACCESS_KEY": "abc123"}):
        with patch("sys.argv", ["kybackup", "restore", str(backup_file)]):
            main()
    assert "Backup restored" in capsys.readouterr().out
