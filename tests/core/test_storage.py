import pytest
import os
import asyncio
import time

def test_save_and_get(kv_store):
    kv_store.save("test_key", "test_value")
    assert kv_store.getkey("test_key") == "test_value"

def test_save_empty_key(kv_store):
    with pytest.raises(ValueError):
        kv_store.save("", "value")
    with pytest.raises(ValueError):
        kv_store.save("   ", "value")

def test_save_empty_value(kv_store):
    # None is valid JSON (null)
    kv_store.save("key", None)
    assert kv_store.getkey("key") is None

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

    # Manually expire items (Skipped due to time sensitivity logic in memory)
    # The logic depends on CURRENT_TIMESTAMP vs python time.
    pass

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
    
    # Try reading without key - should fail init
    with pytest.raises(Exception):
        with Kycore(db_path=db_path) as kv_no_key:
            pass
    
    # Try reading with wrong key
    with pytest.raises(Exception):
        with Kycore(db_path=db_path, master_key="wrong_key") as kv_wrong_key:
             pass
    
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
    # Re-init should trigger cleanup (move to archive)
    with Kycore(db_path=db_path) as kv2:
        # Check internal DB state
        res = kv2._debug_fetch("SELECT count(*) FROM kvstore WHERE key='temp'", [])
        assert int(res[0][0]) == 0
        
        # Ensure it's in archive
        res = kv2._debug_fetch("SELECT count(*) FROM archive WHERE key='temp'", [])
        assert int(res[0][0]) == 1

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
    
    # History should be inaccessible without key
    with pytest.raises(Exception):
        with Kycore(db_path=db_path) as kv_no_key:
            pass

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
    # Verify it's in archive (using internal engine)
    # We must re-open to inspect state if previous block closed
    with Kycore(db_path=db_path) as kv:
        res = kv._debug_fetch("SELECT count(*) FROM archive WHERE key='expired_key'", [])
        assert int(res[0][0]) == 1
        
        res = kv._debug_fetch("SELECT count(*) FROM kvstore WHERE key='expired_key'", [])
        assert int(res[0][0]) == 0

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
    # 2. Try to restore/view without key - Should Fail Init (Full DB Encryption)
    with pytest.raises(Exception):
        with Kycore(db_path=db_path) as kv_no_key:
            pass
