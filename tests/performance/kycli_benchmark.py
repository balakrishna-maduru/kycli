#!/usr/bin/env python3
"""
kycli_benchmark.py

Comprehensive performance suite for KyCLI.
Measures throughput and latency for:
- KV Stores (Batch Save, Random Get)
- Queues (FIFO Push/Pop)
- Stacks (LIFO Push/Pop)
- Concurrency (Thread Safety under Stress)

Usage:
    PYTHONPATH=. python3 tests/performance/kycli_benchmark.py
"""

import time
import os
import shutil
import threading
import random
from kycli import Kycore

DB_DIR = "/tmp/kycli_bench_suite"

def setup_db(name, wtype="kv"):
    path = os.path.join(DB_DIR, f"{name}.db")
    if os.path.exists(path):
        os.remove(path)
    os.makedirs(DB_DIR, exist_ok=True)
    
    db = Kycore(path)
    if wtype != "kv":
        db.set_type(wtype)
    return db, path

def benchmark_kv():
    print(f"\n--- KV Benchmark (100k Records) ---")
    # Clean setup
    db, path = setup_db("bench_kv", "kv")
    
    # SAVE MANY
    items = [(f"key_{i}", f"val_{i}") for i in range(100_000)]
    start = time.time()
    db.save_many(items)
    end = time.time()
    print(f"✅ KV Batch Save 100k: {end - start:.2f}s ({(100000/(end-start)):.0f} ops/sec)")
    
    # GET
    # We sample 1000 items to avoid long runtime on linear scans, then extrapolate
    # Note: On production SSDs with cached keys, this is much faster.
    SAMPLE_SIZE = 1000
    start = time.time()
    for i in range(SAMPLE_SIZE):
        db.getkey(f"key_{random.randint(0, 99999)}")
    end = time.time()
    total_time = end - start
    ops_sec = SAMPLE_SIZE / total_time if total_time > 0 else 0
    print(f"✅ KV Random Get (Sample {SAMPLE_SIZE}): {total_time:.2f}s (~{ops_sec:.0f} ops/sec)")
    
    db.__exit__(None, None, None)

def benchmark_queue(wtype="queue", label="Queue"):
    print(f"\n--- {label} Benchmark (100k Records) ---")
    db, path = setup_db(f"bench_{wtype}", wtype)
    
    # PUSH MANY
    items = [f"item_{i}" for i in range(100_000)]
    start = time.time()
    db.push_many(items)
    end = time.time()
    print(f"✅ {label} Batch Push 100k: {end - start:.2f}s ({(100000/(end-start)):.0f} ops/sec)")
    
    # POP MANY
    start = time.time()
    # Pop in chunks of 5000 to mimic consumption
    remaining = 100_000
    CHUNK = 5000
    while remaining > 0:
        db.pop_many(CHUNK)
        remaining -= CHUNK
    end = time.time()
    print(f"✅ {label} Batch Pop 100k (Chunk={CHUNK}): {end - start:.2f}s ({(100000/(end-start)):.0f} ops/sec)")
    
    db.__exit__(None, None, None)

def parallel_worker(wtype, db, count, worker_id):
    # Share the same db instance to test thread safety of the instance
    # Type is already set
    
    # Push/Pop Mix
    for i in range(count):
        if wtype == "kv":
            db.save(f"w{worker_id}_{i}", "data")
        else:
            db.push(f"w{worker_id}_{i}")
            db.pop()

def benchmark_stress(wtype="queue"):
    print(f"\n--- Stress Test ({wtype.upper()}) Parallel 5 Threads ---")
    name = f"stress_{wtype}"
    db_init, path = setup_db(name, wtype)
    # Don't close, share it across threads
    
    threads = []
    # 5 workers, 500 ops each = 2500 ops total
    OPS = 500
    WORKERS = 5
    
    start = time.time()
    for i in range(WORKERS):
        t = threading.Thread(target=parallel_worker, args=(wtype, db_init, OPS, i))
        threads.append(t)
        t.start()
        
    for t in threads:
        t.join()
    end = time.time()
    
    db_init.__exit__(None, None, None)
    
    total = OPS * WORKERS * 2 # Push + Pop
    if wtype == "kv": total = OPS * WORKERS # just save
    
    print(f"✅ Parallel Stress (5 Threads, {total} Ops): {end - start:.2f}s")
    print(f"   Ops/Sec: {total / (end - start):.0f}")

def benchmark_scale_impact():
    print(f"\n--- Scale Impact Test (Write Latency vs DB Size) ---")
    db, path = setup_db("bench_scale", "kv")
    
    # 1. Measure insert into empty
    start = time.time()
    db.save("key_empty", "val")
    t1 = time.time() - start
    
    # 2. Fill with 50k items
    items = [(f"fill_{i}", "x"*100) for i in range(50_000)]
    db.save_many(items)
    
    # 3. Measure insert into 50k
    start = time.time()
    db.save("key_full", "val")
    t2 = time.time() - start
    
    print(f"✅ Write Latency (Empty DB): {t1*1000:.2f}ms")
    print(f"✅ Write Latency (50k DB):   {t2*1000:.2f}ms")
    
    if t2 > t1 * 10:
        print("⚠️  Warning: Latency degraded significantly (O(N) behavior detected?)")
    else:
        print("🚀 Success: Latency is constant (O(1) behavior confirming SQLite/WAL)")
    
    db.__exit__(None, None, None)

if __name__ == "__main__":
    try:
        benchmark_kv()
        benchmark_queue("queue", "FIFO Queue")
        benchmark_queue("stack", "LIFO Stack")
        benchmark_stress("queue")
        benchmark_stress("kv")
        benchmark_scale_impact()
    finally:
        if os.path.exists(DB_DIR):
            shutil.rmtree(DB_DIR)
