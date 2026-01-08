import time
import os
import random
import string
import asyncio
from pydantic import BaseModel
from kycli import Kycore

# --- Pydantic Schema for Scaling Benchmarks ---
class SchoolClass(BaseModel):
    name: str
    grade: int
    teacher: str
    students_count: int

def generate_random_string(length=10):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

def benchmark_op(name, func, iterations=1000):
    start_time = time.perf_counter()
    for _ in range(iterations):
        func()
    end_time = time.perf_counter()
    total_time = end_time - start_time
    avg_time = total_time / iterations
    print(f"{name:<25}: Total={total_time:7.4f}s, Avg={avg_time*1000:8.4f}ms")
    return avg_time

async def benchmark_op_async(name, func, iterations=1000):
    start_time = time.perf_counter()
    for _ in range(iterations):
        await func()
    end_time = time.perf_counter()
    total_time = end_time - start_time
    avg_time = total_time / iterations
    print(f"{name:<25}: Total={total_time:7.4f}s, Avg={avg_time*1000:8.4f}ms")
    return avg_time

# --- Core Benchmarks ---
def run_core_benchmarks():
    db_path = "bench_core.db"
    if os.path.exists(db_path): os.remove(db_path)
    
    print("\n🚀 --- CORE PERFORMANCE (1,000 Ops) ---")
    with Kycore(db_path) as kv:
        keys = [f"key_{i}" for i in range(1000)]
        values = [generate_random_string(20) for i in range(1000)]
        
        i = [0]
        benchmark_op("Save (New)", lambda: (kv.save(keys[i[0]], values[i[0]]), i.__setitem__(0, i[0]+1)), 1000)
        
        j = [0]
        benchmark_op("Get (Hit)", lambda: (kv.getkey(keys[j[0]]), j.__setitem__(0, (j[0]+1)%1000)), 1000)
        
        # Test L1 Cache Hit (same key)
        benchmark_op("L1 Cache Hit", lambda: kv.getkey(keys[0]), 5000)
        
        benchmark_op("List Keys", lambda: kv.listkeys(), 100)
        benchmark_op("Get History", lambda: kv.get_history(keys[0]), 1000)

    if os.path.exists(db_path): os.remove(db_path)

# --- Scaling Benchmarks ---
def run_scaling_benchmarks():
    db_path = "bench_scaling.db"
    if os.path.exists(db_path): os.remove(db_path)
    
    print("\n📈 --- SCALING & BATCH (10,000 Records) ---")
    with Kycore(db_path, schema=SchoolClass) as kv:
        keys = [f"class:{i}" for i in range(10000)]
        values = [{
            "name": f"Class {i}",
            "grade": (i % 12) + 1,
            "teacher": f"Teacher {i}",
            "students_count": 20 + (i % 10)
        } for i in range(10000)]
        
        i = [0]
        benchmark_op("Save Class (Pydantic)", lambda: (kv.save(keys[i[0]], values[i[0]]), i.__setitem__(0, i[0]+1)), 10000)
        
        j = [0]
        benchmark_op("Get Class", lambda: (kv.getkey(keys[j[0]]), j.__setitem__(0, (j[0]+1)%10000)), 10000)
        
        # Batch Save
        batch_data = [(f"batch_{i}", values[i % 10000]) for i in range(1000)]
        start = time.perf_counter()
        kv.save_many(batch_data)
        end = time.perf_counter()
        print(f"{'Batch Save (1000 items)':<25}: Total={end-start:7.4f}s, Avg={(end-start)/1000*1000:8.4f}ms/item")

        # FTS Search
        benchmark_op("Search (FTS Limit 100)", lambda: kv.search("Teacher", limit=100), 500)
        
        print("Optimizing FTS Index...")
        kv.optimize_index()
        benchmark_op("Search (Post-Opt)", lambda: kv.search("Teacher", limit=100), 500)

    if os.path.exists(db_path): os.remove(db_path)

# --- Async Benchmarks ---
async def run_async_benchmarks():
    db_path = "bench_async.db"
    if os.path.exists(db_path): os.remove(db_path)
    
    print("\n🌐 --- ASYNC PERFORMANCE ---")
    with Kycore(db_path) as kv:
        keys = [f"akey_{i}" for i in range(1000)]
        values = [generate_random_string(30) for i in range(1000)]
        
        i = [0]
        async def b_save():
            await kv.save_async(keys[i[0]], values[i[0]])
            i[0] += 1
        await benchmark_op_async("Save Async", b_save, 1000)
        
        j = [0]
        async def b_get():
            await kv.getkey_async(keys[j[0]])
            j[0] = (j[0] + 1) % 1000
        await benchmark_op_async("Get Async", b_get, 1000)

    if os.path.exists(db_path): os.remove(db_path)

def run_all():
    print("="*50)
    print("KYCLI UNIFIED PERFORMANCE BENCHMARK")
    print("="*50)
    run_core_benchmarks()
    run_scaling_benchmarks()
    asyncio.run(run_async_benchmarks())
    print("\n" + "="*50)

if __name__ == "__main__":
    run_all()
