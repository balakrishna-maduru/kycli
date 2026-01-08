import pytest
import os
import json
from kycli import Kycore

def test_dot_notation_retrieval(kv_store):
    data = {
        "user": {
            "profile": {
                "name": "Balu",
                "email": "balu@example.com"
            },
            "settings": {"theme": "dark"}
        }
    }
    kv_store.save("u1", data)
    
    # Exact match works
    assert kv_store.getkey("u1") == data
    
    # Path traversal works
    assert kv_store.getkey("u1.user.profile.name") == "Balu"
    assert kv_store.getkey("u1.user.profile.email") == "balu@example.com"
    assert kv_store.getkey("u1.user.settings.theme") == "dark"
    
    # Missing fields return error string
    assert "KeyError" in kv_store.getkey("u1.user.profile.age")
    assert "TypeError" in kv_store.getkey("u1.user.profile.name.first")

def test_list_indexing_and_slicing(kv_store):
    logs = ["log1", "log2", "log3", "log4", "log5"]
    kv_store.save("logs", logs)
    
    # Single index
    assert kv_store.getkey("logs[0]") == "log1"
    assert kv_store.getkey("logs[4]") == "log5"
    assert kv_store.getkey("logs[-1]") == "log5"
    
    # Slicing
    assert kv_store.getkey("logs[0:2]") == ["log1", "log2"]
    assert kv_store.getkey("logs[2:]") == ["log3", "log4", "log5"]
    assert kv_store.getkey("logs[:2]") == ["log1", "log2"]
    assert kv_store.getkey("logs[1:-1]") == ["log2", "log3", "log4"]
    
    # Errors
    assert "IndexError" in kv_store.getkey("logs[10]")
    assert "TypeError" in kv_store.getkey("logs.level")

def test_nested_complex_queries(kv_store):
    data = {
        "users": [
            {"name": "Alice", "tags": ["admin", "dev"]},
            {"name": "Bob", "tags": ["user"]}
        ]
    }
    kv_store.save("data", data)
    
    assert kv_store.getkey("data.users[0].name") == "Alice"
    assert kv_store.getkey("data.users[0].tags[1]") == "dev"
    assert kv_store.getkey("data.users[1].tags") == ["user"]

def test_atomic_patching(kv_store):
    kv_store.save("config", {"api": {"url": "http://v1", "timeout": 30}})
    
    # Patch existing depth
    kv_store.patch("config.api.timeout", 60)
    res = kv_store.getkey("config")
    assert res["api"]["timeout"] == 60
    assert res["api"]["url"] == "http://v1"
    
    # Patch new depth (create dicts)
    kv_store.patch("config.db.port", 5432)
    res = kv_store.getkey("config")
    assert res["db"]["port"] == 5432
    
    # Patch list index
    kv_store.save("list", [1, 2, 3])
    kv_store.patch("list[1]", 20)
    assert kv_store.getkey("list") == [1, 20, 3]
    
    # Append via index out of range
    kv_store.patch("list[5]", 60)
    res = kv_store.getkey("list")
    assert res[5] == 60
    assert res[3] is None # Filled with None

def test_patch_create_if_not_exists(kv_store):
    # Patch a non-existent key with leading dot
    kv_store.patch("new_user.profile.name", "Maduru")
    assert kv_store.getkey("new_user.profile.name") == "Maduru"
    
    # Patch a non-existent key with leading bracket
    kv_store.patch("new_list[2]", "third")
    res = kv_store.getkey("new_list")
    assert isinstance(res, list)
    assert res[2] == "third"
    assert len(res) == 3

def test_list_push_remove(kv_store):
    kv_store.save("tags", ["python", "cython"])
    
    # Push
    kv_store.push("tags", "sqlite")
    assert "sqlite" in kv_store.getkey("tags")
    
    # Push Unique
    kv_store.push("tags", "python", unique=True)
    assert kv_store.getkey("tags").count("python") == 1
    
    # Remove
    kv_store.remove("tags", "cython")
    assert "cython" not in kv_store.getkey("tags")
    assert kv_store.remove("tags", "missing") == "nochange"
    
    # Errors
    kv_store.save("not_list", "string")
    with pytest.raises(TypeError, match="is not a list"):
        kv_store.push("not_list", "item")
    with pytest.raises(TypeError, match="is not a list"):
        kv_store.remove("not_list", "item")

def test_long_prefix_matching(kv_store):
    # We want to make sure kyg a.b.c works even if both 'a' and 'a.b' are valid keys
    kv_store.save("a", {"b": {"c": 1}})
    kv_store.save("a.b", {"c": 2})
    
    # Should prefer the shortest path to matching prefix? 
    # Actually the current logic tries longest prefix first (for i in range(len(k), 0, -1))
    assert kv_store.getkey("a.b.c") == 2 # 'a.b' is the prefix
    
    # If we want to reach 1:
    assert kv_store.getkey("a.b") == {"c": 2} # exact match wins
    
def test_navigate_edge_cases(kv_store):
    kv_store.save("data", {"a": 1})
    
    # Empty path
    assert kv_store._navigate({"a": 1}, "") == {"a": 1}
    
    # Malformed navigation string (not caught by regex)
    # The current regex matches anything not containing . [ ] or whitespace as an attribute
    assert "KeyError" in kv_store._navigate({"a": 1}, "!!!")

def test_patch_edge_cases(kv_store):
    # Patch None
    kv_store.patch("p1.name", "Balu")
    assert kv_store.getkey("p1.name") == "Balu"
    
    # Patch non-dict to dict conversion
    kv_store.save("p2", "string")
    kv_store.patch("p2.key", "val") # Should overwrite string with dict
    assert kv_store.getkey("p2.key") == "val"

def test_pydantic_schema(kv_store):
    from pydantic import BaseModel
    class User(BaseModel):
        name: str
        age: int

    kv_with_schema = kv_store.__class__(db_path=kv_store.data_path, schema=User)
    kv_with_schema.save("u1", {"name": "Balu", "age": 30})
    assert kv_with_schema.getkey("u1")["name"] == "Balu"
    
    with pytest.raises(ValueError, match="Schema Validation Error"):
        kv_with_schema.save("u2", {"name": "Invalid"})

def test_fts_search(kv_store):
    kv_store.save("doc1", "The quick brown fox jumps over the lazy dog")
    kv_store.save("doc2", "A fast movement of the brown animal")
    kv_store.save("json_doc", {"title": "Structured Data", "content": "Searching inside JSON"})

    results = kv_store.search("brown")
    assert "doc1" in results
    assert "doc2" in results
    assert len(results) == 2
