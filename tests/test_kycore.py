import pytest
import os

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

def test_get_nonexistent_key(kv_store):
    assert kv_store.getkey("nonexistent") == "Key not found"

def test_delete_key(kv_store):
    kv_store.save("to_delete", "value")
    assert kv_store.delete("to_delete") == "Deleted"
    assert kv_store.getkey("to_delete") == "Key not found"

def test_delete_nonexistent_key(kv_store):
    assert kv_store.delete("ghost") == "Key not found"

def test_save_status(kv_store):
    assert kv_store.save("status", "1") == "created"
    assert kv_store.save("status", "2") == "overwritten"
    assert kv_store.save("status", "2") == "nochange"

def test_history_tracking(kv_store):
    kv_store.save("audit", "v1")
    kv_store.save("audit", "v2")
    kv_store.save("audit", "v3")
    
    history = kv_store.get_history("audit")
    assert len(history) == 3
    assert history[0][1] == "v3"  # Index 0 is key, Index 1 is value
    assert history[1][1] == "v2"
    assert history[2][1] == "v1"
    
    # Test all history
    all_history = kv_store.get_history("-h")
    assert len(all_history) >= 3
    assert all_history[0][0] == "audit"

def test_export_import_csv(kv_store, tmp_path):
    kv_store.save("csv_key", "csv_val")
    export_file = str(tmp_path / "data.csv")
    kv_store.export_data(export_file, "csv")
    
    # Create a new store to import data
    new_store = kv_store.__class__(db_path=str(tmp_path / "new.db"))
    new_store.import_data(export_file)
    assert new_store.getkey("csv_key") == "csv_val"

def test_export_import_json(kv_store, tmp_path):
    kv_store.save("json_key", "json_val")
    export_file = str(tmp_path / "data.json")
    kv_store.export_data(export_file, "json")
    
    new_store = kv_store.__class__(db_path=str(tmp_path / "new_json.db"))
    new_store.import_data(export_file)
    assert new_store.getkey("json_key") == "json_val"
