# 🔑 kycli — High-Performance Key-Value Toolkit

`kycli` is a lightweight, blazing-fast key-value storage engine built with **Cython** and linked directly against the **Raw SQLite C API (`libsqlite3`)**. It offers both a robust Command Line Interface (CLI) for terminal productivity and a high-performance, asynchronous Python library API.

[![Python Version](https://img.shields.io/badge/python-3.9+-blue.svg)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## ⚡ Performance: Redefining "Fast"

By removing the Python `sqlite3` wrapper and using direct C-level interactions, `kycli` achieves microsecond-level latency that rivals in-memory stores like Redis.

| Operation | Implementation | Avg Latency | Comparison |
| :--- | :--- | :--- | :--- |
| **Get Key** | **Direct C API** | **0.0028 ms** (2.8 µs) | **150x faster** than standard Python wrappers |
| **Get Key** | **Async (Threadpool)** | 0.0432 ms | Ideal for high-throughput backends |
| **Save Key** | **Atomic Sync** | 0.1895 ms | Durable Disk I/O |

---

## 🚀 Quick Start

### Installation
```bash
pip install kycli
```

### Basic Terminal Flow
```bash
# Save a secret
kys my_api_key "sk-proj-12345"

# Retrieve it (Microsecond speed)
kyg my_api_key

# List everything with Regex support
kyl "api_.*"
```

---

## 💻 CLI Usage

The CLI is designed to be intuitive and safe, featuring **overwrite protection** and **atomic operations**.

| Command | Action | Example |
| :--- | :--- | :--- |
| `kys` | **Save** a value | `kys username "balu"` |
| `kyg` | **Get** a value (supports Regex) | `kyg "user.*"` |
| `kyl` | **List** keys (supports Regex) | `kyl "prod_.*"` |
| `kyv` | **View** history/audit logs | `kyv username` |
| `kyd` | **Delete** a key | `kyd old_token` |
| `kye` | **Export** data (CSV/JSON) | `kye data.json json` |
| `kyi` | **Import** data | `kyi backup.csv` |

---

## 🐍 Python Library API

### Synchronous (High-Speed)
```python
from kycli import Kycore

with Kycore() as core:
    # Set and Get (Dict-style)
    core['app:mode'] = 'production'
    print(core['app:mode'])  # 2.8 µs retrieval
```

### Asynchronous (High-Throughput)
Perfect for FastAPI, Sanic, or any `asyncio` based application.
```python
import asyncio
from kycli import Kycore

async def main():
    with Kycore() as core:
        # Non-blocking async operations
        await core.save_async('session:id', 'xyz789')
        val = await core.getkey_async('session:id')
        print(f"Fetched: {val}")

asyncio.run(main())
```

---

## 🏗 Integration & Usage in Apps

### Within a Class
You can easily wrap `Kycore` within your own application logic to manage state or configuration.

```python
from kycli import Kycore

class AppConfig:
    def __init__(self):
        self.db = Kycore()

    def set_env(self, env: str):
        self.db.save("env", env)

    def get_env(self):
        return self.db.getkey("env")

    def __del__(self):
        # Ensure connection is closed if not using context manager
        if hasattr(self, 'db'):
            # Close connection manually
            self.db.__exit__(None, None, None)

config = AppConfig()
config.set_env("staging")
print(f"Current Environment: {config.get_env()}")
```

### Dependency in FastAPI
KyCLI's asynchronous methods make it a perfect fit for modern web frameworks.

```python
from fastapi import FastAPI, Depends
from kycli import Kycore

app = FastAPI()

# Simple Dependency
def get_kv():
    with Kycore() as core:
        yield core

@app.get("/settings/{key}")
async def get_setting(key: str, kv: Kycore = Depends(get_kv)):
    # Use async method to prevent blocking the event loop
    value = await kv.getkey_async(key)
    return {"key": key, "value": value}

@app.post("/settings/")
async def save_setting(key: str, value: str, kv: Kycore = Depends(get_kv)):
    status = await kv.save_async(key, value)
    return {"status": status, "key": key}
```

---

## 🛡️ Key Features
- **Raw C Integration**: Direct binding to `libsqlite3` for zero abstraction overhead.
- **Asynchronous I/O**: Offloaded database tasks using thread-pools for non-blocking execution.
- **Audit Logging**: Full history of key-value changes kept in an indexed `audit_log` table.
- **Overwrite Protection**: Interactive (Y/N) confirmation prevents accidental data loss.
- **Atomic Operations**: Exports and imports use temporary staging to prevent file corruption.

---

## 🛠 Architecture

- **Engine**: SQLite 3 (WAL Mode enabled for high concurrency).
- **Core**: Compiled via Cython to machine code.
- **Security**: Keys are lowercased and stripped automatically to maintain data integrity.

---

## 👤 Author

**Balakrishna Maduru**  
- [GitHub](https://github.com/balakrishna-maduru)  
- [LinkedIn](https://www.linkedin.com/in/balakrishna-maduru)  
- [Twitter](https://x.com/krishonlyyou)
