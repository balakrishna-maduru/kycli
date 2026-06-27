import os
import sqlite3
from datetime import datetime, timedelta, timezone

from kycli.cli import _maybe_migrate_legacy_sqlite, _next_backup_path, _parse_legacy_expires_at


def test_parse_legacy_expires_at_formats():
    assert _parse_legacy_expires_at(None) is None
    assert _parse_legacy_expires_at(1700000000) is not None
    assert _parse_legacy_expires_at("2026-01-01 10:00:00") is not None
    assert _parse_legacy_expires_at("") is None


def test_next_backup_path(tmp_path):
    base = tmp_path / "db.bak"
    assert _next_backup_path(str(base)) == str(base)
    base.write_text("x")
    assert _next_backup_path(str(base)) == str(base) + ".1"


def test_maybe_migrate_legacy_sqlite_non_sqlite(tmp_path):
    path = tmp_path / "file.bin"
    path.write_bytes(b"not sqlite")
    assert _maybe_migrate_legacy_sqlite(str(path)) is False


def test_maybe_migrate_legacy_sqlite_moves_and_saves(tmp_path, monkeypatch):
    db_path = tmp_path / "legacy.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE kvstore (key TEXT PRIMARY KEY, value TEXT, expires_at DATETIME)"
    )
    future = datetime.now(timezone.utc) + timedelta(seconds=3600)
    exp = future.strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        "INSERT INTO kvstore (key, value, expires_at) VALUES (?, ?, ?)",
        ("KeyOne", "ValueOne", exp),
    )
    conn.commit()
    conn.close()

    saved = []

    class DummyKycore:
        def __init__(self, db_path=None, master_key=None):
            self.db_path = db_path
            self.master_key = master_key

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def save(self, key, value, ttl=None):
            saved.append((key, value, ttl))

    monkeypatch.setattr("kycli.cli.Kycore", DummyKycore)

    result = _maybe_migrate_legacy_sqlite(str(db_path), master_key="pass")
    assert result is True

    backup_base = str(db_path) + ".legacy.sqlite"
    backup_path = backup_base if os.path.exists(backup_base) else backup_base + ".1"
    assert os.path.exists(backup_path)
    assert saved
    assert saved[0][0] == "keyone"
    assert saved[0][1] == "ValueOne"
    assert saved[0][2] is not None
