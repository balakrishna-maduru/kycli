import time
import os
import random
import string
import asyncio
from kycli.kycore import Kycore

def generate_random_string(length=10):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

def benchmark_op(name, func, iterations=1000):
    start_time = time.perf_counter()
    for _ in range(iterations):
        func()
    end_time = time.perf_counter()
    total_time = end_time - start_time
    avg_time = total_time / iterations
    print(f"{name:<20}: Total={total_time:.4f}s, Avg={avg_time*1000:.4f}ms")
    return avg_time

async def benchmark_op_async(name, func, iterations=1000):
    start_time = time.perf_counter()
    for _ in range(iterations):
        await func()
    end_time = time.perf_counter()
    total_time = end_time - start_time
    avg_time = total_time / iterations
    print(f"{name:<20}: Total={total_time:.4f}s, Avg={avg_time*1000:.4f}ms")
    return avg_time

def run_benchmarks():
    db_path = "benchmark_test.db"
    if os.path.exists(db_path):
        os.remove(db_path)
    
    with Kycore(db_path) as kv:
        # Benchmark Save (New Key)
        keys = [f"key_{i}" for i in range(1000)]
        values = [f"val_{i}" for i in range(1000)]
        
        i = 0
        def bench_save():
            nonlocal i
            kv.save(keys[i], values[i])
            i += 1
        
        benchmark_op("Save (New)", bench_save, 1000)
        
        # Benchmark Get
        random_keys = [random.choice(keys) for _ in range(1000)]
        j = 0
        def bench_get():
            nonlocal j
            kv.getkey(random_keys[j])
            j += 1
            
        benchmark_op("Get", bench_get, 1000)
        
        # Benchmark Save (Update)
        k = 0
        def bench_update():
            nonlocal k
            kv.save(keys[k], values[k] + "_updated")
            k += 1
            
        benchmark_op("Save (Update)", bench_update, 1000)
        
        # Benchmark List
        def bench_list():
            kv.listkeys()
            
        benchmark_op("List Keys", bench_list, 1000)

        # Benchmark History
        l = 0
        def bench_history():
            nonlocal l
            kv.get_history(keys[l])
            l += 1
            
        benchmark_op("Get History", bench_history, 1000)

    if os.path.exists(db_path):
        os.remove(db_path)

async def run_benchmarks_async():
    db_path = "benchmark_async.db"
    if os.path.exists(db_path): os.remove(db_path)
    
    with Kycore(db_path) as kv:
        keys = [f"akey_{i}" for i in range(1000)]
        values = [f"aval_{i}" for i in range(1000)]
        
        # Benchmark Async Save
        i = [0]
        async def bench_save_async():
            idx = i[0]
            await kv.save_async(keys[idx], values[idx])
            i[0] += 1
        
        await benchmark_op_async("Save Async (New)", bench_save_async, 1000)
        
        # Benchmark Async Get
        j = [0]
        async def bench_get_async():
            idx = j[0]
            await kv.getkey_async(keys[idx])
            j[0] += 1
            
        await benchmark_op_async("Get Async", bench_get_async, 1000)

    if os.path.exists(db_path): os.remove(db_path)

def run_all_benchmarks():
    print("--- Sync Benchmarks (Raw C API) ---")
    run_benchmarks()
    print("\n--- Async Benchmarks (Non-blocking) ---")
    asyncio.run(run_benchmarks_async())

if __name__ == "__main__":
    run_all_benchmarks()
