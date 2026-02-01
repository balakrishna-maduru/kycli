import pytest
import os
import sqlite3
import shutil
from kycli import Kycore
from datetime import datetime, timezone, timedelta

def test_rotate_master_key(tmp_path):
    db_path = str(tmp_path / "test_rotate.db")
    old_key = "old_secret_key"
    new_key = "new_secret_key"
    
    # 1. Create DB and save some encrypted data
    with Kycore(db_path=db_path, master_key=old_key) as kv:
        kv.save("k1", "v1")
        kv.save("k2", {"foo": "bar"})
        kv.save("k3", [1, 2, 3])
        
        # Verify they are readable
        assert kv.getkey("k1") == "v1"
        assert kv.getkey("k2") == {"foo": "bar"}
        assert kv.getkey("k3") == [1, 2, 3]

    # 2. Rotate to new key
    with Kycore(db_path=db_path, master_key=old_key) as kv:
        count = kv.rotate_master_key(new_key, old_key=old_key)
        # Should rotate 3 values in kvstore, plus audit entries
        assert count >= 3

    # 3. Verify access with new key
    with Kycore(db_path=db_path, master_key=new_key) as kv:
        assert kv.getkey("k1") == "v1"
        assert kv.getkey("k2") == {"foo": "bar"}
        assert kv.getkey("k3") == [1, 2, 3]

    # 4. Verify old key fails
    with pytest.raises(Exception):
        with Kycore(db_path=db_path, master_key=old_key) as kv:
            # Load should fail because the header/blob is re-encrypted
            pass

def test_rotate_master_key_dry_run(tmp_path):
    db_path = str(tmp_path / "test_rotate_dry.db")
    old_key = "old"
    new_key = "new"
    
    with Kycore(db_path=db_path, master_key=old_key) as kv:
        kv.save("k1", "v1")
        
    with Kycore(db_path=db_path, master_key=old_key) as kv:
        count = kv.rotate_master_key(new_key, old_key=old_key, dry_run=True)
        assert count >= 1
        
    # Verify still readable with old key
    with Kycore(db_path=db_path, master_key=old_key) as kv:
        assert kv.getkey("k1") == "v1"

def test_migration_from_legacy_sqlite(tmp_path):
    db_path = str(tmp_path / "legacy.db")
    master_key = "secret"
    
    # 1. Create a legacy SQLite DB manually
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("CREATE TABLE kvstore (key TEXT PRIMARY KEY, value TEXT, expires_at DATETIME)")
    
    # Insert some data (note: legacy format was just plain SQLite, maybe values were already 'enc:...')
    # But for migration test, let's assume raw values
    cur.execute("INSERT INTO kvstore (key, value, expires_at) VALUES (?, ?, ?)", ("k1", "v1", None))
    # Test TTL migration
    future = (datetime.now(timezone.utc) + timedelta(hours=1)).strftime('%Y-%m-%d %H:%M:%S')
    cur.execute("INSERT INTO kvstore (key, value, expires_at) VALUES (?, ?, ?)", ("k2", "v2", future))
    conn.commit()
    conn.close()
    
    # Verify it is a legacy SQLite file
    with open(db_path, "rb") as f:
        assert f.read(15) == b"SQLite format 3"

    # 2. Use cli's _maybe_migrate_legacy_sqlite to migrate
    from kycli.cli import _maybe_migrate_legacy_sqlite
    success = _maybe_migrate_legacy_sqlite(db_path, master_key=master_key)
    assert success is True
    
    # 3. Verify the new DB is encrypted and contains the data
    with Kycore(db_path=db_path, master_key=master_key) as kv:
        assert kv.getkey("k1") == "v1"
        assert kv.getkey("k2") == "v2"
        # Check if TTL was preserved
        # (This depends on internal implementation details of how Kycore handles TTL)
        res = kv._debug_fetch("SELECT expires_at FROM kvstore WHERE key='k2'", [])
        assert res[0][0] is not None
    
    # 4. Verify backup exists
    assert os.path.exists(db_path + ".legacy.sqlite")

def test_rotate_with_invalid_old_key(tmp_path):
    db_path = str(tmp_path / "test_invalid_old.db")
    with Kycore(db_path=db_path, master_key="correct") as kv:
        kv.save("k1", "v1")
        
    with Kycore(db_path=db_path, master_key="correct") as kv:
        with pytest.raises(ValueError, match="Old master key is invalid"):
            kv.rotate_master_key("new", old_key="wrong")
