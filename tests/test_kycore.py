import pytest
import os
import asyncio
import time

def test_save_and_get(kv_store):
    kv_store.save("test_key", "test_value")
    assert kv_store.getkey("test_key") == "test_value"

def test_save_empty_key(kv_store):
    with pytest.raises(ValueError, match="Key cannot be empty"):
        kv_store.save("", "value")
    with pytest.raises(ValueError, match="Key cannot be empty"):
        kv_store.save("   ", "value")

def test_save_empty_value(kv_store):
    with pytest.raises(ValueError, match="Value cannot be empty"):
        kv_store.save("key", "")

def test_dict_interface(kv_store):
    # __setitem__ and __getitem__
    kv_store["hello"] = "world"
    assert kv_store["hello"] == "world"
    
    # __contains__
    assert "hello" in kv_store
    assert "missing" not in kv_store
    
    # __len__
    assert len(kv_store) == 1
    
    # __iter__
    keys = list(kv_store)
    assert keys == ["hello"]
    
    # __delitem__
    del kv_store["hello"]
    assert "hello" not in kv_store
    assert len(kv_store) == 0

def test_async_ops(kv_store):
    res = asyncio.run(kv_store.save_async("async_key", "async_val"))
    assert res == "created"
    
    val = asyncio.run(kv_store.getkey_async("async_key"))
    assert val == "async_val"

def test_archive_and_restore(kv_store):
    kv_store.save("recoverable", "important_data")
    assert kv_store.getkey("recoverable") == "important_data"
    
    # Delete it
    kv_store.delete("recoverable")
    assert kv_store.getkey("recoverable") == "Key not found"
    
    # Restore it
    res = kv_store.restore("recoverable")
    assert "Restored" in res
    assert kv_store.getkey("recoverable") == "important_data"

def test_list_keys(kv_store):
    kv_store.save("key1", "val1")
    kv_store.save("key2", "val2")
    kv_store.save("other", "val3")
    
    keys = kv_store.listkeys()
    assert "key1" in keys
    assert "key2" in keys
    assert "other" in keys
    assert len(keys) == 3

def test_list_keys_pattern(kv_store):
    kv_store.save("user_name", "balu")
    kv_store.save("user_age", "30")
    kv_store.save("app_version", "1.0")
    
    keys = kv_store.listkeys("user_.*")
    assert "user_name" in keys
    assert "user_age" in keys
    assert "app_version" not in keys

def test_auto_purge_logic(kv_store):
    # Simulate old records in archive
    kv_store.save("old_key", "old_val")
    kv_store.delete("old_key")
    
    path = kv_store.data_path
    
    # Close the fixture connection so it doesn't hold any locks or stale state
    kv_store.__exit__(None, None, None)
    
    import sqlite3
    conn = sqlite3.connect(path)
    conn.execute("UPDATE archive SET deleted_at = datetime('now', '-16 days') WHERE key = 'old_key'")
    conn.commit()
    conn.close()
    
    # Re-initialize Kycore - it should perform cleanup during __init__
    new_store = kv_store.__class__(db_path=path)
    
    # Check if 'old_key' is gone from archive (restore should fail)
    res = new_store.restore("old_key")
    assert "No archived version found" in res
    new_store.__exit__(None, None, None)

def test_history_tracking(kv_store):
    kv_store.save("audit", "v1")
    kv_store.save("audit", "v2")
    kv_store.save("audit", "v3")
    
    history = kv_store.get_history("audit")
    assert len(history) == 3
    assert history[0][1] == "v3"
    
def test_export_import_csv(kv_store, tmp_path):
    kv_store.save("csv_key", "csv_val")
    export_file = str(tmp_path / "data.csv")
    kv_store.export_data(export_file, "csv")
    
    new_store = kv_store.__class__(db_path=str(tmp_path / "new.db"))
    new_store.import_data(export_file)
    assert new_store.getkey("csv_key") == "csv_val"
