import time
import json
from kycli import Kycore

def test_performance_patching(kv_store):
    # Setup large JSON
    data = {f"field_{i}": "some large string data for testing" for i in range(100)}
    kv_store.save("large_json", data)
    
    # Measure Patch
    start = time.perf_counter()
    for i in range(100):
        kv_store.patch("large_json.field_50", f"updated_val_{i}")
    end = time.perf_counter()
    avg_patch = (end - start) / 100
    print(f"\nAverage Patch Latency: {avg_patch*1000:.4f} ms")
    assert avg_patch < 0.01 # Expecting < 10ms for partial updates

def test_performance_navigation(kv_store):
    # Setup deep JSON
    data = {"a": {"b": {"c": {"d": {"e": "found"}}}}}
    kv_store.save("deep", data)
    
    # Measure Navigation
    start = time.perf_counter()
    for _ in range(1000):
        kv_store.getkey("deep.a.b.c.d.e")
    end = time.perf_counter()
    avg_nav = (end - start) / 1000
    print(f"Average Navigation Latency: {avg_nav*1000000:.2f} µs")
    assert avg_nav < 0.001 # Expecting < 1ms

def test_performance_push(kv_store):
    # Setup list
    kv_store.save("list", [])
    
    # Measure Push
    start = time.perf_counter()
    for i in range(100):
        kv_store.push("list", f"item_{i}")
    end = time.perf_counter()
    avg_push = (end - start) / 100
    print(f"Average Push Latency: {avg_push*1000:.4f} ms")
    assert avg_push < 0.01
