import time
import os
import asyncio
from kycli import Kycore

def benchmark_op(name, func, iterations=1000):
    start_time = time.perf_counter()
    for _ in range(iterations):
        func()
    end_time = time.perf_counter()
    total_time = end_time - start_time
    avg_time = total_time / iterations
    print(f"{name:<25}: Total={total_time:7.4f}s, Avg={avg_time*1000:8.4f}ms")
    return avg_time

def run_scaling_benchmarks():
    db_path = "benchmark_scaling.db"
    if os.path.exists(db_path):
        os.remove(db_path)
    
    print(f"--- Performance & Scaling Benchmark ---")
    
    with Kycore(db_path, cache_size=1000) as kv:
        # 1. Benchmark Cache Hit vs Miss
        kv.save("cached_key", "value")
        
        # Measure Miss (First fetch after save updates cache, so let's clear it or use a new key)
        # Actually save() already updates cache. Let's force a miss by using a key not in cache initially.
        kv.save("miss_key", "value")
        # To truly test miss, we'd need to bypass cache, but getkey always updates it.
        # Let's test the 'Hit' speed.
        benchmark_op("L1 Cache Hit", lambda: kv.getkey("cached_key"), 10000)

        # 2. Benchmark Batch Save
        batch_data = [(f"batch_key_{i}", f"val_{i}") for i in range(1000)]
        
        start = time.perf_counter()
        kv.save_many(batch_data)
        end = time.perf_counter()
        print(f"Batch Save (1000 items)  : Total={end-start:7.4f}s, Avg={(end-start)/1000*1000:8.4f}ms per item")

        # 3. Benchmark Individual Save vs Batch
        def individual_save():
            for i in range(100):
                kv.save(f"ind_key_{i}", "val")
        
        def batch_save_wrapper():
            kv.save_many([(f"bat_key_{i}", "val") for i in range(100)])

        benchmark_op("Individual Save (x100)", individual_save, 10)
        benchmark_op("Batch Save (x100)", batch_save_wrapper, 10)

        # 4. Replication Stream
        stream = kv.get_replication_stream(last_id=0)
        print(f"Replication Stream Size  : {len(stream)} entries")

    if os.path.exists(db_path):
        os.remove(db_path)

if __name__ == "__main__":
    run_scaling_benchmarks()
