import pytest
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, mock_open, MagicMock
from kycli.cli import main, _parse_legacy_expires_at, _next_backup_path, _maybe_migrate_legacy_sqlite

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


def test_parse_legacy_expires_at_variants():
    dt = _parse_legacy_expires_at(0)
    assert dt == datetime.fromtimestamp(0, tz=timezone.utc)

    assert _parse_legacy_expires_at(" ") is None

    iso_dt = _parse_legacy_expires_at("2026-02-01T10:00:00")
    assert iso_dt.tzinfo == timezone.utc

    fmt_dt = _parse_legacy_expires_at("2026-02-01 10:00:00")
    assert fmt_dt.tzinfo == timezone.utc

    fmt_ms_dt = _parse_legacy_expires_at("2026-02-01 10:00:00.123456")
    assert fmt_ms_dt.tzinfo == timezone.utc

    assert _parse_legacy_expires_at("not a date") is None


def test_parse_legacy_expires_at_strptime_path(monkeypatch):
    import kycli.cli as cli_mod

    real_dt = cli_mod.datetime

    class FakeDateTime:
        @staticmethod
        def fromisoformat(_val):
            raise ValueError("fail")

        @staticmethod
        def strptime(val, fmt):
            return real_dt.strptime(val, fmt)

    monkeypatch.setattr(cli_mod, "datetime", FakeDateTime)
    dt = cli_mod._parse_legacy_expires_at("2026-02-01 10:00:00")
    assert dt.tzinfo == timezone.utc


def test_next_backup_path(tmp_path):
    base = tmp_path / "data.db"
    assert _next_backup_path(str(base)) == str(base)

    base.write_text("x")
    (tmp_path / "data.db.1").write_text("y")
    assert _next_backup_path(str(base)) == str(tmp_path / "data.db.2")


def _create_legacy_db(path, with_expires, rows):
    conn = sqlite3.connect(path)
    if with_expires:
        conn.execute("CREATE TABLE kvstore (key TEXT PRIMARY KEY, value TEXT, expires_at DATETIME)")
        for k, v, exp in rows:
            conn.execute("INSERT INTO kvstore (key, value, expires_at) VALUES (?, ?, ?)", (k, v, exp))
    else:
        conn.execute("CREATE TABLE kvstore (key TEXT PRIMARY KEY, value TEXT)")
        for k, v in rows:
            conn.execute("INSERT INTO kvstore (key, value) VALUES (?, ?)", (k, v))
    conn.commit()
    conn.close()


def test_maybe_migrate_legacy_sqlite_non_sqlite(tmp_path):
    db_path = tmp_path / "legacy.db"
    db_path.write_bytes(b"NOTSQL")
    assert _maybe_migrate_legacy_sqlite(str(db_path)) is False


def test_maybe_migrate_legacy_sqlite_no_expires(tmp_path):
    db_path = tmp_path / "legacy_no_exp.db"
    _create_legacy_db(str(db_path), with_expires=False, rows=[("k1", "v1")])
    assert _maybe_migrate_legacy_sqlite(str(db_path)) is True


def test_maybe_migrate_legacy_sqlite_with_expires(tmp_path):
    db_path = tmp_path / "legacy_exp.db"
    now = datetime.now(timezone.utc)
    future = (now + timedelta(seconds=2)).strftime("%Y-%m-%d %H:%M:%S")
    past = (now - timedelta(seconds=2)).strftime("%Y-%m-%d %H:%M:%S")
    _create_legacy_db(
        str(db_path),
        with_expires=True,
        rows=[("k1", "v1", future), ("k2", "v2", past)],
    )
    assert _maybe_migrate_legacy_sqlite(str(db_path)) is True


def test_maybe_migrate_legacy_sqlite_header_str(tmp_path, monkeypatch):
    db_path = tmp_path / "legacy_header.db"
    _create_legacy_db(str(db_path), with_expires=False, rows=[("k1", "v1")])

    class FakeFile:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self, n):
            return "SQLite format 3\0"

    real_open = open

    def fake_open(path, mode="r", *args, **kwargs):
        if path == str(db_path) and "rb" in mode:
            return FakeFile()
        return real_open(path, mode, *args, **kwargs)

    monkeypatch.setattr("builtins.open", fake_open)
    assert _maybe_migrate_legacy_sqlite(str(db_path)) is True


def test_maybe_migrate_legacy_sqlite_copy_error(tmp_path):
    db_path = tmp_path / "legacy_copy.db"
    _create_legacy_db(str(db_path), with_expires=False, rows=[("k1", "v1")])

    with patch("shutil.copy2", side_effect=OSError("copy failed")):
        assert _maybe_migrate_legacy_sqlite(str(db_path)) is True


def test_maybe_migrate_legacy_sqlite_move_error(tmp_path):
    db_path = tmp_path / "legacy_move.db"
    _create_legacy_db(str(db_path), with_expires=False, rows=[("k1", "v1")])

    with patch("shutil.move", side_effect=OSError("move failed")):
        assert _maybe_migrate_legacy_sqlite(str(db_path)) is False


def test_maybe_migrate_legacy_sqlite_kycore_none(tmp_path, monkeypatch):
    db_path = tmp_path / "legacy_none.db"
    _create_legacy_db(str(db_path), with_expires=False, rows=[("k1", "v1")])

    monkeypatch.setattr("kycli.cli.Kycore", None)
    assert _maybe_migrate_legacy_sqlite(str(db_path)) is False


def test_maybe_migrate_legacy_sqlite_close_error(tmp_path, monkeypatch):
    db_path = tmp_path / "legacy_close.db"
    _create_legacy_db(str(db_path), with_expires=False, rows=[("k1", "v1")])

    class FakeCursor:
        def execute(self, *_args, **_kwargs):
            return None

        def fetchone(self):
            return None

    class FakeConn:
        def cursor(self):
            return FakeCursor()

        def close(self):
            raise OSError("close failed")

    monkeypatch.setattr("sqlite3.connect", lambda *_args, **_kwargs: FakeConn())
    assert _maybe_migrate_legacy_sqlite(str(db_path)) is True


def test_maybe_migrate_legacy_sqlite_null_key(tmp_path, monkeypatch):
    db_path = tmp_path / "legacy_null.db"
    _create_legacy_db(str(db_path), with_expires=True, rows=[("k1", "v1", None)])

    class FakeCursor:
        def __init__(self):
            self.last_sql = ""

        def execute(self, sql, params=None):
            self.last_sql = sql
            return None

        def fetchone(self):
            if "sqlite_master" in self.last_sql:
                return ("kvstore",)
            return None

        def fetchall(self):
            if "PRAGMA table_info" in self.last_sql:
                return [(0, "key"), (1, "value"), (2, "expires_at")]
            if "SELECT key, value, expires_at" in self.last_sql:
                return [(None, "v", None)]
            return []

    class FakeConn:
        def cursor(self):
            return FakeCursor()

        def close(self):
            return None

    monkeypatch.setattr("sqlite3.connect", lambda *_args, **_kwargs: FakeConn())
    assert _maybe_migrate_legacy_sqlite(str(db_path)) is True


def test_cli_invalid_numeric_flags(clean_home_db, capsys):
    mock_kv = MagicMock()
    mock_kv.get_type.return_value = "kv"
    mock_kv.getkey.return_value = "Key not found"
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_kv
    mock_ctx.__exit__.return_value = False

    with patch("kycli.cli.Kycore", return_value=mock_ctx), \
         patch("sys.argv", ["kyg", "--limit", "bad", "--batch", "nope", "--priority", "oops", "missing"]):
        main()
    assert "Key not found" in capsys.readouterr().out


def test_cli_kyrotate_success_default_old_key(clean_home_db, capsys, monkeypatch):
    mock_kv = MagicMock()
    mock_kv.rotate_master_key.return_value = 2
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_kv
    mock_ctx.__exit__.return_value = False

    monkeypatch.setenv("KYCLI_MASTER_KEY", "oldpass")
    with patch("kycli.cli.Kycore", return_value=mock_ctx), \
         patch("sys.argv", ["kyrotate", "--new-key", "newpass"]):
        main()
    assert "Rotation complete" in capsys.readouterr().out


def test_cli_kyrotate_batch_backup(clean_home_db, capsys):
    mock_kv = MagicMock()
    mock_kv.rotate_master_key.return_value = 1
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_kv
    mock_ctx.__exit__.return_value = False

    with patch("kycli.cli.Kycore", return_value=mock_ctx), \
         patch("sys.argv", ["kyrotate", "--new-key", "newpass", "--old-key", "oldpass", "--batch", "10", "--backup"]):
        main()
    assert "Rotation complete" in capsys.readouterr().out


def test_cli_kyrotate_failure(clean_home_db, capsys):
    mock_kv = MagicMock()
    mock_kv.rotate_master_key.side_effect = RuntimeError("boom")
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_kv
    mock_ctx.__exit__.return_value = False

    with patch("kycli.cli.Kycore", return_value=mock_ctx), \
         patch("sys.argv", ["kyrotate", "--new-key", "newpass", "--old-key", "oldpass"]):
        main()
    assert "Rotation failed" in capsys.readouterr().out


def test_cli_kyws_create_errors(clean_home_db, capsys):
    with patch("sys.argv", ["kyws", "create"]):
        main()
    assert "Usage: kyws create" in capsys.readouterr().out

    with patch("sys.argv", ["kyws", "create", "bad/name"]):
        main()
    assert "Invalid workspace name" in capsys.readouterr().out

    with patch("sys.argv", ["kyws", "create", "ws", "--type"]):
        main()
    assert "Usage: kyws create" in capsys.readouterr().out


def test_cli_kyws_create_failure(clean_home_db, capsys):
    mock_kv = MagicMock()
    mock_kv.set_type.side_effect = ValueError("bad type")
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_kv
    mock_ctx.__exit__.return_value = False

    with patch("kycli.cli.Kycore", return_value=mock_ctx), \
         patch("sys.argv", ["kyws", "create", "ws", "--type", "bad"]):
        main()
    assert "Failed to create workspace" in capsys.readouterr().out


def test_cli_kyws_create_success(clean_home_db, capsys):
    mock_kv = MagicMock()
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_kv
    mock_ctx.__exit__.return_value = False

    with patch("kycli.cli.Kycore", return_value=mock_ctx), \
         patch("sys.argv", ["kyws", "create", "ws_ok", "--type", "queue"]):
        main()
    assert "created with type" in capsys.readouterr().out


def test_cli_kydrop_missing_and_active(clean_home_db, capsys, tmp_path):
    with patch("kycli.config.DATA_DIR", str(tmp_path)), \
         patch("os.path.exists", return_value=False), \
         patch("sys.argv", ["kydrop", "missing_ws"]):
        main()
    assert "does not exist" in capsys.readouterr().out

    with patch("kycli.cli.load_config", return_value={"db_path": "x", "active_workspace": "ws1"}), \
         patch("kycli.config.DATA_DIR", str(tmp_path)), \
         patch("os.path.exists", return_value=True), \
         patch("builtins.input", return_value="y"), \
         patch("os.remove"):
        with patch("sys.argv", ["kydrop", "ws1"]):
            main()
    assert "Switched to 'default' workspace" in capsys.readouterr().out


def test_cli_queue_commands_and_clear(clean_home_db, capsys):
    mock_kv = MagicMock()
    mock_kv.get_type.return_value = "queue"
    mock_kv.peek.return_value = "peeked"
    mock_kv.pop.return_value = "popped"
    mock_kv.count.return_value = 2
    mock_kv.clear.return_value = "cleared"
    mock_kv.push.return_value = "pushed"
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_kv
    mock_ctx.__exit__.return_value = False

    with patch("kycli.cli.Kycore", return_value=mock_ctx), \
         patch("sys.argv", ["kypeek"]):
        main()
    assert "peeked" in capsys.readouterr().out

    with patch("kycli.cli.Kycore", return_value=mock_ctx), \
         patch("sys.argv", ["kypop"]):
        main()
    assert "popped" in capsys.readouterr().out

    with patch("kycli.cli.Kycore", return_value=mock_ctx), \
         patch("sys.argv", ["kycount"]):
        main()
    assert "2" in capsys.readouterr().out

    with patch("kycli.cli.Kycore", return_value=mock_ctx), \
         patch("builtins.input", return_value="n"), \
         patch("sys.argv", ["kyclear"]):
        main()
    assert "Aborted" in capsys.readouterr().out

    with patch("kycli.cli.Kycore", return_value=mock_ctx), \
         patch("builtins.input", return_value="y"), \
         patch("sys.argv", ["kyclear"]):
        main()
    assert "cleared" in capsys.readouterr().out

    with patch("kycli.cli.Kycore", return_value=mock_ctx), \
         patch("sys.argv", ["kypush"]):
        main()
    assert "Usage: kypush <value>" in capsys.readouterr().out

    with patch("kycli.cli.Kycore", return_value=mock_ctx), \
         patch("sys.argv", ["kypush", "{\"a\": 1}"]):
        main()
    assert "pushed" in capsys.readouterr().out

    with patch("kycli.cli.Kycore", return_value=mock_ctx), \
         patch("sys.argv", ["kypush", "--priority", "3", "item"]):
        main()
    assert "pushed" in capsys.readouterr().out
