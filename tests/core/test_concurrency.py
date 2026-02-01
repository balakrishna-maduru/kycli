
import pytest
import os
import threading
import time
from kycli import Kycore

DB_PATH = "/tmp/test_concurrency.db"

@pytest.fixture
def clean_db():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    yield DB_PATH
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

def test_parallel_pop_race_condition(clean_db):
    """
    Simulate multiple workers processing a queue simultaneously.
    Goal: Zero duplicates, Zero lost items.
    """
    WORKER_COUNT = 5
    ITEMS_PER_WORKER = 20
    TOTAL_ITEMS = WORKER_COUNT * ITEMS_PER_WORKER
    
    # Setup: Fill Queue
    with Kycore(clean_db) as q:
        q.set_type("queue")
        for i in range(TOTAL_ITEMS):
            q.push(f"job_{i}")
        assert len(q) == TOTAL_ITEMS

    # Shared results container
    results = []
    lock = threading.Lock()
    errors = []

    # Shared instance for thread-safety test
    # Note: This assumes Kycore/SQLite is configured with check_same_thread=False
    # If not, this test will fail, indicating thread-safety issues.
    db = Kycore(clean_db)
    # db.set_type("queue") # Type is already persisted
        
    def worker_task(worker_id):
        try:
            processed_count = 0
            while True:
                # Use shared DB instance
                item = db.pop()
                if item is None:
                    break
                
                with lock:
                    results.append(item)
                
                processed_count += 1
                time.sleep(0.001)
        except Exception as e:
            errors.append(e)

    # Start Threads
    threads = []
    for i in range(WORKER_COUNT):
        t = threading.Thread(target=worker_task, args=(i,))
        threads.append(t)
        t.start()

    # Wait for all
    for t in threads:
        t.join()

    # Validation
    if errors:
        pytest.fail(f"Workers encountered errors: {errors}")

    assert len(results) == TOTAL_ITEMS, f"Expected {TOTAL_ITEMS} items, got {len(results)}"
    
    # Check for Duplicates
    unique_items = set(results)
    assert len(unique_items) == len(results), "Duplicate items detected! Atomic transaction failed."
    
    # Check for Consistency
    expected_set = {f"job_{i}" for i in range(TOTAL_ITEMS)}
    assert unique_items == expected_set, "Some items were lost or incorrect."
    
    # Verify DB is empty
    with Kycore(clean_db) as q:
        assert len(q) == 0

