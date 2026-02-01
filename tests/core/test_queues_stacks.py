
import pytest
import os
import shutil
from kycli import Kycore

DB_PATH = "/tmp/test_queues_stacks.db"

@pytest.fixture
def clean_db():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    yield DB_PATH
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

def test_queue_fifo(clean_db):
    """Test standard FIFO Queue behavior."""
    with Kycore(clean_db) as q:
        q.set_type("queue")
        assert q.get_type() == "queue"
        
        q.push("item1")
        q.push("item2")
        q.push("item3")
        
        assert len(q) == 3
        assert q.peek() == "item1"
        
        assert q.pop() == "item1"
        assert q.pop() == "item2"
        assert q.pop() == "item3"
        assert q.pop() is None # Empty

def test_stack_lifo(clean_db):
    """Test standard LIFO Stack behavior."""
    with Kycore(clean_db) as s:
        s.set_type("stack")
        assert s.get_type() == "stack"
        
        s.push("bottom")
        s.push("middle")
        s.push("top")
        
        assert len(s) == 3
        assert s.peek() == "top"
        
        assert s.pop() == "top"
        assert s.pop() == "middle"
        assert s.pop() == "bottom"
        assert s.pop() is None

def test_priority_queue(clean_db):
    """Test Priority Queue ordering (Higher priority first)."""
    with Kycore(clean_db) as pq:
        pq.set_type("priority_queue")
        
        pq.push("low", priority=1)
        pq.push("high", priority=100)
        pq.push("medium", priority=50)
        
        assert len(pq) == 3
        
        # Order should be: High, Medium, Low
        assert pq.pop() == "high"
        assert pq.pop() == "medium"
        assert pq.pop() == "low"

def test_aggregations_and_clear(clean_db):
    """Test Count and Clear methods."""
    with Kycore(clean_db) as q:
        q.set_type("queue")
        for i in range(10):
            q.push(f"item_{i}")
            
        assert len(q) == 10
        assert q.count() == 10
        
        # Clear
        q.clear()
        assert len(q) == 0
        assert q.pop() is None

def test_strict_compatibility_negative(clean_db):
    """Ensure KV commands fail on Queue/Stack and vice-versa."""
    # 1. KV Command on Queue
    with Kycore(clean_db) as q:
        q.set_type("queue")
        
        with pytest.raises(TypeError) as exc:
            q.save("some_key", "val")
        assert "'kys' not supported" in str(exc.value)

        with pytest.raises(TypeError) as exc:
            q.getkey("some_key")
        assert "'kyg' not supported" in str(exc.value)

    # 2. Queue Command on KV
    if os.path.exists(DB_PATH): os.remove(DB_PATH)
    with Kycore(clean_db) as kv:
        # Implicitly KV
        assert kv.get_type() == "kv"
        
        with pytest.raises(TypeError) as exc:
            kv.pop()
        assert "'pop' not supported" in str(exc.value)
        
        with pytest.raises(TypeError) as exc:
            kv.push("value_only") # Missing key
        assert "requires a 'key' argument" in str(exc.value)

def test_metadata_persistence(clean_db):
    """Test that workspace type is persisted across sessions."""
    # Session 1: Create
    with Kycore(clean_db) as db:
        db.set_type("priority_queue")
        db.push("val1", priority=10)
    
    # Session 2: Reopen
    with Kycore(clean_db) as db2:
        assert db2.get_type() == "priority_queue"
        assert len(db2) == 1
        assert db2.pop() == "val1"
        
        # Cannot change type
        with pytest.raises(ValueError):
            db2.set_type("stack")

