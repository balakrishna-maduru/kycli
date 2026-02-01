# ⚡ KyCLI Performance Benchmarks

`kycli` is built for high-performance secure storage. It uses **Record-Level Encryption**, ensuring that while your data is secure at rest, operations remain O(1) and scale efficiently with database size.

## 📊 Summary Results (100,000 Records)
Benchmarks run on Apple Silicon (M-series), record-level encryption enabled.

| Operation | Throughput | Latency per Op | Implementation |
| :--- | :--- | :--- | :--- |
| **KV Batch Save** | **~53,000 ops/sec** | **0.019 ms** | SQL Transaction (O(1)) |
| **KV Random Get** | **~85,000 ops/sec** | **0.012 ms** | Indexed Lookup + Record Decrypt |
| **Queue Push (Bulk)** | **~290,000 ops/sec** | **0.003 ms** | SQL Transaction (WAL) |
| **Stack Push (Bulk)** | **~310,000 ops/sec** | **0.003 ms** | SQL Transaction (WAL) |
| **Queue Pop (Bulk)** | **~280,000 ops/sec** | **0.003 ms** | Atomic `BEGIN IMMEDIATE` + Batch Delete |
| **Stack Pop (Bulk)** | **~110,000 ops/sec** | **0.009 ms** | Atomic `BEGIN IMMEDIATE` + Batch Delete |

## 🚀 Concurrency & Stress Tests
`kycli` leverages SQLite **WAL Mode**, providing excellent performance under high concurrency and multi-process safety.

| Scenario | Throughput | Description |
| :--- | :--- | :--- |
| **Parallel Queue (5 Threads)** | **~36,000 ops/sec** | Concurrent `push` + `pop`. No global locks. |
| **Parallel KV (5 Threads)** | **~10,000 ops/sec** | Concurrent individual `save` operations. O(1) performance. |

### 🧠 Performance Insights

1.  **O(1) Scalability**: Write latency is constant regardless of database size. `kycli` no longer rewrites the entire file for every store operation.
2.  **Optimized Reads**: Simple key lookups skip full-table scans. Regex search is only triggered for patterns containing metacharacters.
3.  **Durability**: Every write is committed to disk using SQLite's Write-Ahead Log (WAL), ensuring data integrity in the event of a crash.
4.  **Concurrency**: WAL mode allows multiple readers and one writer simultaneously, making `kycli` suitable for multi-threading and multi-process environments.

## 🛠️ Reproduction
Run the benchmark suite yourself:
```bash
PYTHONPATH=. python3 tests/performance/kycli_benchmark.py
```
*(Ensure you have rebuilt the Cython extension with `python setup.py build_ext --inplace`)*
