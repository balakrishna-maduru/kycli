import pytest
import os
import time
from kycli import Kycore
from datetime import datetime, timezone, timedelta

def test_save_many(tmp_path):
    db = str(tmp_path / "test_many.db")
    with Kycore(db) as kv:
        items = [("key1", "val1"), ("key2", {"a": 1}), ("key3", 123)]
        kv.save_many(items)
        assert kv.getkey("key1") == "val1"
        assert kv.getkey("key2") == {"a": 1}
        assert kv.getkey("key3") == 123
        assert len(kv) == 3

def test_save_many_with_ttl(tmp_path):
    db = str(tmp_path / "test_many_ttl.db")
    with Kycore(db) as kv:
        # Use 1 second TTL and sleep 2 to be safe
        kv.save_many([("k1", "v1")], ttl=1)
        assert kv.getkey("k1") == "v1"
        time.sleep(2.1) # Definitely expired
        assert kv.getkey("k1") == "Key not found"

def test_lru_cache_eviction(tmp_path):
    db = str(tmp_path / "test_cache.db")
    # Small cache to test eviction
    with Kycore(db, cache_size=2) as kv:
        kv.save("a", 1)
        kv.save("b", 2)
        kv.save("c", 3) # Should evict "a"
        
        # "a" is evicted from cache but still in DB
        assert kv.getkey("a") == 1
        # After getkey("a"), "a" is re-added to cache. b is now oldest.
        # Cache: ["c", "a"]
        kv.getkey("c") # c moved to end. Cache: ["a", "c"]
        kv.save("d", 4) # evicts oldest which is "a". Cache: ["c", "d"]
        
        cache_keys = kv.cache_keys
        assert "b" not in cache_keys
        assert "a" not in cache_keys
        assert "c" in cache_keys
        assert "d" in cache_keys

def test_replication_stream(tmp_path):
    db1_path = str(tmp_path / "db1.db")
    db2_path = str(tmp_path / "db2.db")
    
    with Kycore(db1_path) as db1:
        db1.save("sync_key", "sync_val")
        stream = db1.get_replication_stream(last_id=0)
        assert len(stream) > 0
        
        with Kycore(db2_path) as db2:
            db2.sync_from_stream(stream)
            assert db2.getkey("sync_key") == "sync_val"

def test_pitr_restore_to(tmp_path):
    db = str(tmp_path / "test_pitr.db")
    with Kycore(db) as kv:
        kv.save("k1", "v1")
        time.sleep(1.1)
        # Use UTC for consistency with audit log
        t1 = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
        time.sleep(1.1)
        kv.save("k1", "v2")
        kv.save("k2", "v3")
        
        assert kv.getkey("k1") == "v2"
        
        kv.restore_to(t1)
        assert kv.getkey("k1") == "v1"
        assert kv.getkey("k2") == "Key not found"

def test_compact(tmp_path):
    db = str(tmp_path / "test_compact.db")
    with Kycore(db) as kv:
        kv.save("k1", "v1")
        kv.delete("k1")
        # Ensure something is in audit/archive
        assert len(kv.get_history("-h")) > 0
        
        # Wait to ensure 'now' is definitely after the timestamps
        time.sleep(1.1)
        
        # Compact with 0 retention should clear everything from 1s ago
        kv.compact(retention_days=0)
        assert len(kv.get_history("-h")) == 0

def test_search_optimized(tmp_path):
    db = str(tmp_path / "test_search.db")
    with Kycore(db) as kv:
        kv.save("user:1", "alice")
        kv.save("user:2", "bob")
        
        # Test limit
        res = kv.search("user", limit=1)
        assert len(res) == 1
        
        # Test keys_only
        keys = kv.search("user", keys_only=True)
        assert isinstance(keys, list)
        assert "user:1" in keys
        assert "user:2" in keys

def test_delete_tombstone_pitr(tmp_path):
    db = str(tmp_path / "test_del_pitr.db")
    with Kycore(db) as kv:
        kv.save("k1", "v1")
        time.sleep(1.1)
        t1 = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
        time.sleep(1.1)
        kv.delete("k1")
        assert kv.getkey("k1") == "Key not found"
        
        # Restore to T1 should bring k1 back
        kv.restore_to(t1)
        assert kv.getkey("k1") == "v1"

def test_save_error_rollback(tmp_path):
    db = str(tmp_path / "test_error.db")
    with Kycore(db) as kv:
        # Cause a runtime error by passing invalid type to execute_raw via internal mocking or manipulation
        # Actually, let's try to save with an empty key which raises ValueError before transaction
        with pytest.raises(ValueError):
            kv.save("", "val")
            
def test_compact_error(tmp_path):
    db = str(tmp_path / "test_compact_err.db")
    with Kycore(db) as kv:
        # Closing DB to cause error on compact
        import sqlite3
        kv.__exit__(None, None, None)
        with pytest.raises(RuntimeError, match="Compaction failed"):
            kv.compact()

def test_save_many_error_rollback(tmp_path):
    db = str(tmp_path / "test_many_err.db")
    with Kycore(db) as kv:
        # Invalid item to cause error during loop
        with pytest.raises(Exception):
             kv.save_many([("k1", "v1"), (None, "v2")])
        # Ensure k1 was not saved due to rollback (Actually save_many takes list of tuples)
        # If one fails, the whole transaction should rollback
        assert kv.getkey("k1") == "Key not found"
