
import pytest
import os
import threading
import time
import multiprocessing
from kycli import Kycore

DB_PATH = "/tmp/test_concurrency.db"


def _mp_worker_push(db_path, worker_id, n_items, ready_evt, start_evt):
    """Each call opens its OWN Kycore instance against the shared db_path,
    simulating independent `kycli` CLI invocations racing on one workspace."""
    kv = Kycore(db_path)
    ready_evt.set()
    start_evt.wait(timeout=10)
    for i in range(n_items):
        kv.push(f"w{worker_id}_item_{i}")
    kv.__exit__(None, None, None)

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


def test_multiprocess_push_zero_loss_zero_corruption(tmp_path):
    """
    Simulate multiple independent `kycli` processes (separate Kycore
    instances, separate OS processes) pushing to the same workspace file
    concurrently. Goal: Zero lost items, zero corruption/crashes.
    """
    db_path = str(tmp_path / "mp_queue.db")
    N_PROCS = 4
    N_ITEMS = 50

    with Kycore(db_path) as kv:
        kv.set_type("queue")

    ctx = multiprocessing.get_context("spawn")
    start_evt = ctx.Event()
    ready_evts = [ctx.Event() for _ in range(N_PROCS)]
    procs = [
        ctx.Process(target=_mp_worker_push, args=(db_path, i, N_ITEMS, ready_evts[i], start_evt))
        for i in range(N_PROCS)
    ]
    for p in procs:
        p.start()
    for e in ready_evts:
        e.wait(timeout=10)
    start_evt.set()
    for p in procs:
        p.join(timeout=30)

    assert all(p.exitcode == 0 for p in procs), "A worker crashed (likely file corruption)"

    with Kycore(db_path) as kv:
        total = N_PROCS * N_ITEMS
        assert kv.count() == total, f"Expected {total} items, found {kv.count()} (lost updates)"
        seen = set()
        while True:
            item = kv.pop()
            if item is None:
                break
            assert item not in seen, "Duplicate item popped"
            seen.add(item)
        assert len(seen) == total

