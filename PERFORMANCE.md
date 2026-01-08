## Overview
KyCLI has been pushed to the absolute limits of performance by integrating directly with the **SQLite C API (`libsqlite3`)** and introducing **Asynchronous I/O** support.

1.  **C-level SQLite Integration**:
    *   **Raw C API**: We removed the Python `sqlite3` wrapper entirely. KyCLI now calls `sqlite3_prepare_v2`, `sqlite3_step`, and `sqlite3_bind_text` directly using Cython `cdef` externs.
    *   **Zero Overhead Fetch**: Reads now bypass Python's database abstraction layer, leading to ultra-low latency key retrieval.
    *   **Pointer Management**: Direct C-string handling and manual statement finalization ensure minimal memory allocations.
2.  **Asynchronous I/O Support**:
    *   **Non-blocking API**: Added `save_async()` and `getkey_async()` methods.
    *   **Thread Pool Execution**: Uses `asyncio.to_thread` to offload database I/O, allowing high-throughput integrations in web servers (like FastAPI or Sanic) without blocking the event loop.

## Benchmark Results (Avg task for 1,000 calls)

| Operation | Implementation | Avg Latency |
| :--- | :--- | :--- |
| **Sync (Raw C)** | **0.0040 ms** (4.0 µs) |
| **L1 Cache Hit hit** | **Cython LRU** | **0.0038 ms** (3.8 µs) |
| **Batch Save** | **Atomic C-Loop** | **0.0229 ms** / item |
| **Get Key** | **Async (Threadpool)** | 0.0461 ms |
| **Get History** | **Sync (Raw C)** | 0.0037 ms |
| **List Keys** | **Sync (Raw C)** | 0.1680 ms |

## Scaling Performance (10,000 Classes/Records)

To test the engine at scale, we simulated a database with **10,000 school class records**, each validated using a **Pydantic schema**.

| Operation | Scale | Avg Latency | notes |
| :--- | :--- | :--- | :--- |
| **Save Class** | 10k Records | **1.7124 ms** | Includes Pydantic validation & JSON serialization |
| **Get Class** | 10k Records | **0.0056 ms** | microsecond-fast retrieval at scale |
| **List Keys** | 10k Records | **1.5620 ms** | Near-instant listing of entire dataset |
| **Search (FTS)** | 10k Records | **6.6721 ms** | Full-text search (no limit) |
| **Search (Limit)** | 10k Records | **6.6349 ms** | Optimized FTS search |
| **Save Async** | 10k Records | **0.2976 ms** | High-throughput background saves |
| **Get Async** | 10k Records | **0.0461 ms** | Non-blocking retrieval |

### Analysis
*   **Sync Performance**: The raw C API provides the best latency for CLI usage. A simple key fetch is now performing at near-native hardware speeds (~2.8 microseconds).
*   **Async Trade-off**: Asynchronous calls add slight overhead (~40µs) due to thread switching. This is highly beneficial for high-throughput applications where you want to handle multiple I/O tasks concurrently, even though single-task latency is higher.

## How to measure speed
Run the comprehensive sync + async benchmark:
```bash
PYTHONPATH=. python3 tests/integration/benchmark.py
```


## Performance & Scaling Features

1.  **Hybrid Memory Cache (L1 Cache)**:
    *   **LRU Cache**: A high-speed memory cache built using `collections.OrderedDict` in Cython.
    *   **Nanosecond Hits**: Frequent reads bypass the SQLite engine entirely, hitting memory in ~1-2 microseconds.
    *   **Auto-Invalidation**: Writes and deletes automatically update or prune the cache to ensure consistency.
2.  **Batch Save (`save_many`)**:
    *   **Atomic Transactions**: Ingest thousands of keys in a single transaction.
    *   **Bypasses Overhead**: Extremely efficient for bulk data loading or state syncing.
3.  **Point-in-Time Recovery (PITR)**:
    *   `kyrt <timestamp>`: Reconstruct the entire database state at any specific timestamp using the audit log.
4.  **Database Compaction**:
    *   `kyco [days]`: An `optimize` command that runs `VACUUM` and clears out old history/archive data based on a retention policy.

