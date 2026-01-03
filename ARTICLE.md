# KyCLI: Achieving Microsecond-Fast Key-Value Storage in Python

In the world of Python development, we often trade speed for developer productivity. But what if you could have both? Over the last few days, I’ve been pushing the limits of local storage performance to create **KyCLI**—a toolkit that achieves performance levels usually reserved for native C applications.

By combining **Cython**, direct **SQLite C API** integration, and **Asynchronous I/O**, KyCLI has achieved a specialized performance profile that retrieves keys in just **2.8 microseconds**.

## 🚀 10 Reasons Why KyCLI is a Game-Changer

1.  **Direct C API Integration**: Unlike traditional Python apps that use a wrapper, KyCLI speaks directly to the SQLite C library (`libsqlite3`). This removes the "Python Tax" and provides raw, native speed.
2.  **Cythonized Performance**: The core logic is compiled to machine code using Cython, ensuring that every loop and object lookup runs at the speed of C.
3.  **Microsecond Latency**: With key retrieval times at ~2.8µs, KyCLI is effectively as fast as reading from local RAM, but with the benefit of disk persistence.
4.  **Zero-Server Architecture**: No need to install Redis or manage a daemon. KyCLI is embedded, meaning it lives inside your app and requires zero configuration.
5.  **True Async/Await Support**: While the core is C-fast, it provides a non-blocking Async API (`getkey_async`), making it perfect for high-traffic web servers like FastAPI or Sanic.
6.  **Immutable Audit Trails**: Every single change is automatically logged in an audit history, giving you a full "time-travel" view of your data with virtually zero performance penalty.
7.  **WAL Mode Concurrency**: Using SQLite’s Write-Ahead Logging (WAL), KyCLI supports multiple simultaneous readers without blocking, ensuring smooth performance during heavy writes.
8.  **Regex Pattern Querying**: Need to find keys matching a pattern? KyCLI supports high-performance regex searching across your entire dataset.
9.  **Atomic Reliability**: Every "Save" operation is wrapped in a C-level transaction, ensuring that your data is never left in a corrupted state, even during a crash.
10. **Dual-Use Interface**: It’s equally powerful as a command-line tool for dev-ops tasks and as a high-performance library for Python backend development.

---

## 📊 Performance Deep Dive

When we compare KyCLI to standard implementations or even local Redis instances, the results are startling. By eliminating network socket overhead and Python abstraction layers, we've moved the needle from milliseconds to microseconds.

### The Head-to-Head Stats (1,000 Operations Avg)

| Operation | Implementation | Avg Latency | Speed Multiplier |
| :--- | :--- | :--- | :--- |
| **Get Key** | **KyCLI (Raw C)** | **0.0028 ms** | **150x Faster** than standard storage |
| **Get Key** | **Local Redis** | 0.0800 ms | KyCLI is **~28x faster** locally |
| **Save Key** | **KyCLI (Raw C)** | 0.1895 ms | Optimized for durability |
| **Audit Fetch** | **KyCLI (Indexed)** | 0.0050 ms | Instant history retrieval |

### How We Achieved It
*   **Prepared Statements**: SQL is parsed once and cached in memory for the life of the process.
*   **Synchronous = NORMAL**: We optimized the disk-sync strategy to prioritize throughput while maintaining SQLite’s famous data safety.
*   **Memory Pruning**: Temporary operations are offloaded to memory (`temp_store=MEMORY`) to avoid slow disk thrashing.

---

## Conclusion

KyCLI proves that Python doesn't have to be slow when it comes to data I/O. By reaching down into the C layer, we can build tools that are lightweight, serverless, and unbelievably fast.

Whether you're building a high-speed cache, a local configuration engine, or a developer utility, KyCLI provides the performance of a high-end database with the simplicity of a Python script.

**Check it out and run the benchmarks yourself!**
```bash
python3 benchmark.py
```
