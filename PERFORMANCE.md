## Overview
KyCLI has been pushed to the absolute limits of performance by integrating directly with the **SQLite C API (`libsqlite3`)** and introducing **Asynchronous I/O** support.

1.  **C-level SQLite Integration**:
    *   **Raw C API**: We removed the Python `sqlite3` wrapper entirely. KyCLI now calls `sqlite3_prepare_v2`, `sqlite3_step`, and `sqlite3_bind_text` directly using Cython `cdef` externs.
    *   **Zero Overhead Fetch**: Reads now bypass Python's database abstraction layer, leading to ultra-low latency key retrieval.
    *   **Pointer Management**: Direct C-string handling and manual statement finalization ensure minimal memory allocations.
2.  **Asynchronous I/O Support**:
    *   **Non-blocking API**: Added `save_async()` and `getkey_async()` methods.
    *   **Thread Pool Execution**: Uses `asyncio.to_thread` to offload database I/O, allowing high-throughput integrations in web servers (like FastAPI or Sanic) without blocking the event loop.

## Benchmark Results (Avg task for 1000 calls)

| Operation | Implementation | Avg Latency |
| :--- | :--- | :--- |
| **Get Key** | **Sync (Raw C)** | **0.0028 ms** (2.8 µs) |
| **Get Key** | **Async (Threadpool)** | 0.0432 ms |
| **Save Key** | **Sync (Raw C)** | 0.1895 ms |
| **Save Key** | **Async (Threadpool)** | 0.2547 ms |
| **Get History** | **Sync (Raw C)** | 0.0050 ms |
| **List Keys** | **Sync (Raw C)** | 0.1506 ms |

### Analysis
*   **Sync Performance**: The raw C API provides the best latency for CLI usage. A simple key fetch is now performing at near-native hardware speeds (~2.8 microseconds).
*   **Async Trade-off**: Asynchronous calls add slight overhead (~40µs) due to thread switching. This is highly beneficial for high-throughput applications where you want to handle multiple I/O tasks concurrently, even though single-task latency is higher.

## How to measure speed
Run the comprehensive sync + async benchmark:
```bash
python3 benchmark.py
```

## Advanced Optimizations Implemented
*   **WAL Mode**: Write-Ahead Logging allows simultaneous reads and writes.
*   **Prepared Statements**: Cached statement handles reduce SQL parsing time.
*   **Indexed Auditing**: Fast history traversal using B-Tree indexes on keys.
*   **Memory Pruning**: SQLite `temp_store=MEMORY` avoids disk thrashing for intermediate results.
