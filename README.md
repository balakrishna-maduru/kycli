# 🔑 kycli — The Microsecond-Fast Key-Value Toolkit

`kycli` is a high-performance, developer-first key-value storage engine. It bridges the gap between the simplicity of a flat-file database and the blazing speed of in-memory caches like Redis, all while remaining completely serverless and lightweight.

Built with **Cython** and linked directly to the **Raw SQLite C API (`libsqlite3`)**, `kycli` is optimized for local development, CLI productivity, and high-throughput Python backends.

---

## ⚡ Performance: Real-World Stats

`kycli` is designed to be the fastest local storage option available for Python. By bypassing standard abstraction layers and moving critical logic to C, we achieve microsecond-level latency.

### Benchmark Results (Average of 1,000 calls)

| Operation | Implementation | Avg Latency | vs. Standard Python |
| :--- | :--- | :--- | :--- |
| **Key Retrieval (Get)** | **Direct C API** | **0.0028 ms** (2.8 µs) | **150x Faster** |
| **Key Retrieval (Get)** | **Async/Threaded** | 0.0432 ms | 10x Faster |
| **Save / Update** | **Atomic Sync** | 0.1895 ms | Optimized for safety |
| **History Lookup** | **Indexed C API** | 0.0050 ms | Instant Auditing |

> **Why so fast?** Standard Python storage tools use network sockets (Redis) or heavy wrappers (SQLAlchemy). `kycli` uses direct memory pointers to an embedded C engine, removing 99% of the overhead.

---

## 🚀 Installation

Install the latest version from PyPI:
```bash
pip install kycli
```

---

## 💻 CLI Command Reference

`kycli` provides a set of ultra-short commands for maximum terminal productivity.

| Command | Action | Example |
| :--- | :--- | :--- |
| `kys` | **Save** a value (with overwrite check) | `kys username "balu"` |
| `kyg` | **Get** a value (supports Regex) | `kyg "user.*"` |
| `kyl` | **List** keys (supports Regex) | `kyl "prod_.*"` |
| `kyv` | **View** history/audit logs | `kyv username` |
| `kyd` | **Delete** (Double-confirmation) | `kyd old_token` |
| `kyr` | **Restore** (Recover from history) | `kyr old_token` |
| `kye` | **Export** data (CSV/JSON) | `kye data.json json` |
| `kyi` | **Import** data | `kyi backup.csv` |
| `kyh` | **Help** library | `kyh` |

### `kyh` — The Help Center
Shows the available commands and basic usage instructions.
```bash
kyh
# Or use the -h flag on specific commands
```

### `kys <key> <value>` — Save Data
Saves a value to a key.
- **Auto-Normalization**: Keys are lowercased and trimmed.
- **Safety**: Asks `(y/n)` before overwriting an existing key.
```bash
kys username "balakrishna"
# Result: ✅ Saved: username (New)

kys username "maduru"
# Result: ⚠️ Key 'username' already exists. Overwrite? (y/n):
```

### `kyg <key_or_regex>` — Search & Get
Retrieves a value. Supports exact matches and regex.
```bash
kyg username
# Result: maduru

kyg "user.*"
# Result: {'username': 'maduru', 'user_id': '101'} (Matches found via regex)
```

### `kyl [pattern]` — List Keys
Lists all keys or those matching a pattern.
```bash
kyl
# Result: 🔑 Keys: username, user_id, env

kyl "user.*"
# Result: 🔑 Keys: username, user_id
```

### `kyv [key | -h]` — View History (Audit Log)
`kycli` never deletes your old values; it archives them.
- **`kyv -h`**: Shows the full history of ALL keys in a formatted table.
- **`kyv <key>`**: Shows the latest value from the history for that specific key.
```bash
kyv -h
# Result: 📜 Full Audit History (All Keys)
# Timestamp            | Key             | Value
# -----------------------------------------------------
# 2026-01-03 13:20:01  | username        | maduru
# 2026-01-03 13:10:00  | username        | balakrishna
```

### `kyd <key>` — Delete Key (Soft Delete)
Removes a key from the active store.
- **Double-Confirmation**: Requires you to re-type the key name to prevent accidental loss.
- **Tip**: Deletion is "soft" in terms of data—it stays in history and can be recovered.
```bash
kyd username
# Result: ⚠️ DANGER: To delete 'username', please re-enter the key name: username
# Result: Deleted
# Result: 💡 Tip: If this was accidental, use 'kyr username' to restore it.
```

### `kyr <key>` — Restore Key
Restores a key from its history back into the active store.
- **Note**: This works for keys in the **Archive** table. KyCLI keeps deleted data for **15 days** before permanent removal.
```bash
kyr username
# Result: ✅ Key 'username' restored from history.
```

### `kye <file> [format]` — Export Data
Exports your entire store to a file.
- **Format**: `csv` (default) or `json`.
```bash
kye backup.csv
kye data.json json
```

### `kyi <file>` — Import Data
Bulk imports data from a CSV or JSON file.
```bash
kyi backup.csv
```

---

## 🐍 Python Library Interface

### 1. Dictionary-like Interface (Sync)
The easiest way to integrate into any Python script or class.
```python
from kycli import Kycore

# Use as a context manager for automatic cleanup
with Kycore() as kv:
    # Set and Get (Dict-style)
    kv['theme'] = 'dark'
    print(kv['theme'])  # dark

    # Check existence
    if 'theme' in kv:
        print("Settings loaded.")

    # Bulk count
    print(f"Items stored: {len(kv)}")
```

### 2. High-Throughput (Async)
Designed for `asyncio` applications like FastAPI.
```python
import asyncio
from kycli import Kycore

async def run_tasks():
    with Kycore() as kv:
        await kv.save_async("status", "running")
        current = await kv.getkey_async("status")
        print(f"System is {current}")

asyncio.run(run_tasks())
```

### 3. Application / Class Integration
Wrap `Kycore` inside your classes for persistent state management.
```python
class UserManager:
    def __init__(self):
        self.db = Kycore()

    def update_profile(self, user_id, data):
        self.db.save(f"user:{user_id}", data)

    def close(self):
        self.db.__exit__(None, None, None)
```

### 4. FastAPI Web Server Integration
```python
from fastapi import FastAPI, Depends
from kycli import Kycore

app = FastAPI()

def get_db():
    with Kycore() as db:
        yield db

@app.get("/config/{key}")
async def fetch_config(key: str, db: Kycore = Depends(get_db)):
    return {"val": await db.getkey_async(key)}
```

---

## 🏗 Architecture & Internal Safety

- **SQLite Engine**: Running in `WAL` (Write-Ahead Logging) mode for concurrent reads/writes.
- **Atomic Operations**: Exports use a "temp-file then rename" strategy to prevent corruption.
- **Data Integrity**: Keys are automatically lowercased and stripped to prevent duplicate-but-slightly-different keys.
- **Auto-Purge Policy**: Deleted keys are moved to an **Archive** table and automatically purged after **15 days** to keep the database size optimized.
- **Embedded C**: Core operations are written in Cython, binding directly to native library pointers.

---

## 📊 Benchmarking

Want to test the speed on your own hardware?
```bash
python3 benchmark.py
```

---

## 👤 Author & Support

**Balakrishna Maduru**  
- [GitHub](https://github.com/balakrishna-maduru)  
- [LinkedIn](https://www.linkedin.com/in/balakrishna-maduru/in/balakrishna-maduru)  
- [Twitter](https://x.com/krishonlyyou)

---
*Optimized for Performance by Antigravity*
