import time
import os
import random
import string
import asyncio
from pydantic import BaseModel
from kycli import Kycore

class SchoolClass(BaseModel):
    name: str
    grade: int
    teacher: str
    students_count: int

def generate_random_string(length=10):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

def benchmark_op(name, func, iterations=10000):
    start_time = time.perf_counter()
    for _ in range(iterations):
        func()
    end_time = time.perf_counter()
    total_time = end_time - start_time
    avg_time = total_time / iterations
    print(f"{name:<25}: Total={total_time:7.4f}s, Avg={avg_time*1000:8.4f}ms")
    return avg_time

async def benchmark_op_async(name, func, iterations=10000):
    start_time = time.perf_counter()
    for _ in range(iterations):
        await func()
    end_time = time.perf_counter()
    total_time = end_time - start_time
    avg_time = total_time / iterations
    print(f"{name:<25}: Total={total_time:7.4f}s, Avg={avg_time*1000:8.4f}ms")
    return avg_time

def run_10k_benchmarks():
    db_path = "benchmark_10k.db"
    if os.path.exists(db_path):
        os.remove(db_path)
    
    print(f"--- 10,000 Records Benchmark (with Pydantic Schema) ---")
    
    # We use the schema just for the Save part to simulate "making 10000 class"
    with Kycore(db_path, schema=SchoolClass) as kv:
        # Data preparation
        keys = [f"class:{i}" for i in range(10000)]
        values = [{
            "name": f"Class {i}",
            "grade": (i % 12) + 1,
            "teacher": f"Teacher {i}",
            "students_count": 20 + (i % 10)
        } for i in range(10000)]
        
        i = [0]
        def bench_save():
            idx = i[0]
            kv.save(keys[idx], values[idx])
            i[0] += 1
        
        benchmark_op("Save Class (New)", bench_save, 10000)
        
        # Benchmark Get
        random_keys = [random.choice(keys) for _ in range(10000)]
        j = [0]
        def bench_get():
            idx = j[0]
            kv.getkey(random_keys[idx])
            j[0] += 1
            
        benchmark_op("Get Class", bench_get, 10000)
        
        # Benchmark List
        def bench_list():
            kv.listkeys()
            
        benchmark_op("List 10,000 Keys", bench_list, 1000) # List is slower, 1000 iterations is enough for a good avg

        # Benchmark Search (FTS) - Old style (Fetching all 10k matches)
        def bench_search_all():
            kv.search("Teacher", limit=10000)
            
        benchmark_op("Search (All 10k)", bench_search_all, 100)

        # Benchmark Search (FTS) - Optimized (Limit 100)
        def bench_search_limit():
            kv.search("Teacher", limit=100)
            
        benchmark_op("Search (Limit 100)", bench_search_limit, 1000)

        # Benchmark Search (FTS) - Keys Only (Limit 100)
        def bench_search_keys():
            kv.search("Teacher", limit=100, keys_only=True)
            
        benchmark_op("Search (Keys Only)", bench_search_keys, 1000)

        # Optimize Index
        print("Optimizing FTS Index...")
        kv.optimize_index()

        benchmark_op("Search (Post-Opt)", bench_search_limit, 1000)

    if os.path.exists(db_path):
        os.remove(db_path)

async def run_10k_benchmarks_async():
    db_path = "benchmark_10k_async.db"
    if os.path.exists(db_path): os.remove(db_path)
    
    print(f"\n--- 10,000 Records Async Benchmark ---")
    
    with Kycore(db_path) as kv:
        keys = [f"akey_{i}" for i in range(10000)]
        values = [f"aval_{i}" for i in range(10000)]
        
        # Benchmark Async Save
        i = [0]
        async def bench_save_async():
            idx = i[0]
            await kv.save_async(keys[idx], values[idx])
            i[0] += 1
        
        await benchmark_op_async("Save Async (New)", bench_save_async, 10000)
        
        # Benchmark Async Get
        j = [0]
        async def bench_get_async():
            idx = j[0]
            await kv.getkey_async(keys[idx])
            j[0] += 1
            
        await benchmark_op_async("Get Async", bench_get_async, 10000)

    if os.path.exists(db_path): os.remove(db_path)

if __name__ == "__main__":
    run_10k_benchmarks()
    asyncio.run(run_10k_benchmarks_async())
