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
    with pytest.raises(ValueError, match="Value cannot be None"):
        kv_store.save("key", None)

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

def test_json_doc(kv_store):
    # Test saving a dictionary
    data = {"name": "Balu", "age": 30, "nested": {"key": "val"}}
    kv_store.save("user:1", data)
    
    # Retrieve and check type
    result = kv_store.getkey("user:1")
    assert isinstance(result, dict)
    assert result["name"] == "Balu"
    assert result["nested"]["key"] == "val"
    
    # Test saving a list
    list_data = [1, 2, 3, "four"]
    kv_store.save("my_list", list_data)
    res_list = kv_store.getkey("my_list")
    assert isinstance(res_list, list)
    assert res_list[3] == "four"

def test_fts_search(kv_store):
    kv_store.save("doc1", "The quick brown fox jumps over the lazy dog")
    kv_store.save("doc2", "A fast movement of the brown animal")
    kv_store.save("json_doc", {"title": "Structured Data", "content": "Searching inside JSON"})

    # Search for "brown"
    results = kv_store.search("brown")
    assert "doc1" in results
    assert "doc2" in results
    assert len(results) == 2

    # Search for "Structured"
    results = kv_store.search("Structured")
    assert "json_doc" in results
    assert results["json_doc"]["title"] == "Structured Data"

def test_pydantic_schema(kv_store):
    from pydantic import BaseModel
    
    class User(BaseModel):
        name: str
        age: int

    # Initialize with schema
    kv_with_schema = kv_store.__class__(db_path=kv_store.data_path, schema=User)
    
    # Valid save
    kv_with_schema.save("u1", {"name": "Balu", "age": 30})
    assert kv_with_schema.getkey("u1")["name"] == "Balu"
    
    # Invalid save (missing age)
    with pytest.raises(ValueError, match="Schema Validation Error"):
        kv_with_schema.save("u2", {"name": "Invalid"})
    
    with pytest.raises(ValueError, match="Schema Validation Error"):
        kv_with_schema.save("u3", {"name": "Balu", "age": "thirty"})

def test_schema_init_error(kv_store):
    # Pass a non-model class
    class NotAModel:
        pass
    
    with pytest.raises(TypeError, match="Schema must be a Pydantic BaseModel class"):
        kv_store.__class__(db_path=kv_store.data_path, schema=NotAModel)

def test_save_mixed_types(kv_store):
    # Integer as value
    kv_store.save("int_key", 123)
    assert kv_store.getkey("int_key") == 123 # Json loads will get int back
    
    # Boolean as value
    kv_store.save("bool_key", True)
    assert kv_store.getkey("bool_key") is True
    
    # Float as value
    kv_store.save("float_key", 3.14)
    assert kv_store.getkey("float_key") == 3.14

def test_getkey_no_deserialize(kv_store):
    kv_store.save("json_raw", {"a": 1})
    # deserialize=False should return raw JSON string
    res = kv_store.getkey("json_raw", deserialize=False)
    assert isinstance(res, str)
    assert '{"a": 1}' in res

def test_search_no_deserialize(kv_store):
    kv_store.save("search_raw", {"b": 2})
    res = kv_store.search("b", deserialize=False)
    assert "search_raw" in res
    assert isinstance(res["search_raw"], str)

def test_encryption_at_rest(tmp_path):
    from kycli import Kycore
    db_path = str(tmp_path / "encrypted.db")
    master_key = "secure_key_123"
    
    with Kycore(db_path=db_path, master_key=master_key) as kv:
        kv.save("secret", "top_secret_data")
        assert kv.getkey("secret") == "top_secret_data"
    
    # Try reading without key - should see warning message
    with Kycore(db_path=db_path) as kv_no_key:
        raw_val = kv_no_key.getkey("secret")
        assert "ENCRYPTED" in raw_val
    
    # Try reading with wrong key
    with Kycore(db_path=db_path, master_key="wrong_key") as kv_wrong_key:
        assert kv_wrong_key.getkey("secret") == "[DECRYPTION FAILED: Incorrect master key]"
    
    # Correct key again
    with Kycore(db_path=db_path, master_key=master_key) as kv_correct:
        assert kv_correct.getkey("secret") == "top_secret_data"

def test_value_level_ttl(kv_store):
    # Save with 1 second TTL
    kv_store.save("expiring", "gone_soon", ttl=1)
    assert kv_store.getkey("expiring") == "gone_soon"
    
    # Wait for expiration
    time.sleep(2.5)
    
    # Should be gone with a warning
    with pytest.warns(UserWarning, match="expired at"):
        assert kv_store.getkey("expiring") == "Key not found"
    
    assert "expiring" not in kv_store
    assert len(kv_store) == 0

def test_ttl_cleanup_on_init(tmp_path):
    from kycli import Kycore
    db_path = str(tmp_path / "ttl_cleanup.db")
    
    with Kycore(db_path=db_path) as kv:
        kv.save("temp", "data", ttl=1)
        assert kv.getkey("temp") == "data"
    
    # Wait for expiration
    time.sleep(2.5)
    
    # Re-init should trigger cleanup (move to archive)
    with Kycore(db_path=db_path) as kv2:
        # Check raw database to ensure it's deleted from kvstore
        import sqlite3
        conn = sqlite3.connect(db_path)
        cursor = conn.execute("SELECT count(*) FROM kvstore WHERE key='temp'")
        count = cursor.fetchone()[0]
        assert count == 0
        
        # Ensure it's in archive
        cursor = conn.execute("SELECT count(*) FROM archive WHERE key='temp'")
        archive_count = cursor.fetchone()[0]
        conn.close()
        assert archive_count == 1

def test_encryption_with_json(tmp_path):
    from kycli import Kycore
    db_path = str(tmp_path / "enc_json.db")
    master_key = "json_secret"
    data = {"complex": [1, 2, {"a": "b"}]}
    
    with Kycore(db_path=db_path, master_key=master_key) as kv:
        kv.save("json_key", data)
        res = kv.getkey("json_key")
        assert res == data
        assert isinstance(res, dict)

def test_encryption_history(tmp_path):
    from kycli import Kycore
    db_path = str(tmp_path / "enc_history.db")
    master_key = "history_secret"
    
    with Kycore(db_path=db_path, master_key=master_key) as kv:
        kv.save("h", "v1")
        kv.save("h", "v2")
        
        history = kv.get_history("h")
        assert history[0][1] == "v2"
        assert history[1][1] == "v1"
    
    # History should be masked on disk if no key provided
    with Kycore(db_path=db_path) as kv_no_key:
        history = kv_no_key.get_history("h")
        assert "ENCRYPTED" in history[0][1]

def test_human_readable_ttl(kv_store):
    # test 1s
    kv_store.save("t_1s", "val", ttl="1s")
    assert kv_store.getkey("t_1s") == "val"
    time.sleep(2.5)
    with pytest.warns(UserWarning, match="expired at"):
        assert kv_store.getkey("t_1s") == "Key not found"
    
    # test 2s as "2s"
    kv_store.save("t_2s", "val", ttl="2s")
    assert kv_store.getkey("t_2s") == "val"
    time.sleep(1)
    assert kv_store.getkey("t_2s") == "val"
    time.sleep(2.5)
    with pytest.warns(UserWarning, match="expired at"):
        assert kv_store.getkey("t_2s") == "Key not found"

def test_parse_ttl_logic(kv_store):
    assert kv_store._parse_ttl("1s") == 1
    assert kv_store._parse_ttl("1m") == 60
    assert kv_store._parse_ttl("1h") == 3600
    assert kv_store._parse_ttl("1d") == 86400
    assert kv_store._parse_ttl("1w") == 604800
    assert kv_store._parse_ttl("1M") == 2592000
    assert kv_store._parse_ttl("1y") == 31536000
    assert kv_store._parse_ttl(100) == 100
    assert kv_store._parse_ttl("100") == 100
    
    with pytest.raises(ValueError, match="Invalid TTL format"):
        kv_store._parse_ttl("10x")

def test_expired_key_archival(tmp_path):
    from kycli import Kycore
    import sqlite3
    db_path = str(tmp_path / "archive_test.db")
    
    # Try retrieving - should warn and move to archive
    with Kycore(db_path=db_path) as kv:
        kv.save("expired_key", "value", ttl=1)
        # Wait for expiration
        time.sleep(2.5)
        with pytest.warns(UserWarning, match="expired at"):
            res = kv.getkey("expired_key")
            assert res == "Key not found"
            
    # Verify it's in archive
    conn = sqlite3.connect(db_path)
    cursor = conn.execute("SELECT count(*) FROM archive WHERE key='expired_key'")
    count = cursor.fetchone()[0]
    conn.close()
    assert count == 1
    
    # Verify it's gone from kvstore
    conn = sqlite3.connect(db_path)
    cursor = conn.execute("SELECT count(*) FROM kvstore WHERE key='expired_key'")
    count = cursor.fetchone()[0]
    conn.close()
    assert count == 0

    # Test ACTUAL retrieval (restore)
    with Kycore(db_path=db_path) as kv:
        res = kv.restore("expired_key")
        assert "Restored" in res
        assert kv.getkey("expired_key") == "value"

def test_archive_security_no_key(tmp_path):
    from kycli import Kycore
    db_path = str(tmp_path / "security_test.db")
    master_key = "very-secret"
    
    # 1. Save and delete with key
    with Kycore(db_path=db_path, master_key=master_key) as kv:
        kv.save("secret_key", "highly_sensitive_data")
        kv.delete("secret_key")
        
    # 2. Try to restore/view without key
    with Kycore(db_path=db_path) as kv_no_key:
        # Restore works, but value is masked
        kv_no_key.restore("secret_key")
        restored_val = kv_no_key.getkey("secret_key")
        assert "ENCRYPTED" in restored_val
        assert "Provide a master key" in restored_val
        
        # History also shows masked info
        history = kv_no_key.get_history("secret_key")
        assert "ENCRYPTED" in history[0][1]
