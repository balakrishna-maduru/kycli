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
