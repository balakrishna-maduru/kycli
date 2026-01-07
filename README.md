# 🔑 kycli — The Microsecond-Fast Key-Value Toolkit

`kycli` is a high-performance, developer-first key-value storage engine. It bridges the gap between the simplicity of a flat-file database and the blazing speed of in-memory caches like Redis, all while remaining completely serverless and lightweight.

Built with **Cython** and linked directly to the **Raw SQLite C API (`libsqlite3`)**, `kycli` is optimized for local development, CLI productivity, and high-throughput Python backends.

---

## ⚡ Performance: Real-World Stats

`kycli` is designed to be the fastest local storage option available for Python. By bypassing standard abstraction layers and moving critical logic to C, we achieve microsecond-level latency.

### Benchmark Results (Average of 1,000 calls)

| **Operation** | **Implementation** | **Avg Latency** | **vs. Standard Python** |
| :--- | :--- | :--- | :--- |
| **L1 Cache Hit** | **Cython LRU** | **1.5 µs** | **Near-In-Memory** |
| **Key Retrieval (Get)** | **Direct C API** | **2.8 µs** | **150x Faster** |
| **Batch Save** | **Atomic C-Loop** | **15 µs / item** | **Extreme Throughput** |
| **History Lookup** | **Indexed C API** | 5.0 µs | Instant Auditing |

> **Why so fast?** Standard Python storage tools use network sockets (Redis) or heavy wrappers (SQLAlchemy). `kycli` uses direct memory pointers to an embedded C engine, removing 99% of the overhead.
>
> **Scaling**: In a benchmark of **10,000 class records** with Pydantic validation, `kycli` maintains a sub-2ms write latency and microsecond-fast reads. See [PERFORMANCE.md](PERFORMANCE.md) for full details.

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
| `kys` | **Save** a value (Supports JSON) | `kys user '{"id": 1}'` |
| `kyg` | **Get** a value (Auto-deserializes) | `kyg user` |
| `kyf` | **Search** (Full-Text Search) | `kyf "search terms"` |
| `kyl` | **List** keys (supports Regex) | `kyl "prod_.*"` |
| `kyv` | **View** history/audit logs | `kyv username` |
| `kyd` | **Delete** (Double-confirmation) | `kyd old_token` |
| `kyr` | **Restore** (Recover from history) | `kyr old_token` |
| `kye` | **Export** data (CSV/JSON) | `kye data.json json` |
| `kyi` | **Import** data | `kyi backup.csv` |
| `kyc` | **Execute** stored command | `kyc hello` |
| `kyrt` | **Restore-to** (Time Machine) | `kyrt "2026-01-01"` |
| `kyco` | **Compact** (Cleanup) | `kyco 7` |
| `kyshell` | **Interactive TUI** | `kycli kyshell` |
| `kyh` | **Help** library | `kyh` |
| `Env` | **KYCLI_DB_PATH** | `export KYCLI_DB_PATH="..."` |

### `kyh` — The Help Center
Shows the available commands and basic usage instructions.
```bash
kyh
# Or use the -h flag on specific commands
```

### `kys <key> <value> [--ttl <sec>]` — Save Data
Saves a value to a key.
- **Auto-Normalization**: Keys are lowercased and trimmed.
- **Safety**: Asks `(y/n)` before overwriting an existing key.
- **TTL (Time To Live)**: Set an expiration time in seconds.
```bash
kys username "balakrishna"
# Result: ✅ Saved: username (New)

kys username "maduru"
# Result: ⚠️ Key 'username' already exists. Overwrite? (y/n):

kys session_id "data" --ttl 1h
# Result: ✅ Saved: session_id (New) (Expires in 1 hour)
```

### 🔐 Enterprise-Grade Security: Encryption at Rest
`kycli` supports transparent **AES-256-GCM** encryption. When a master key is provided, all data is encrypted before being written to disk and decrypted on retrieval.

#### Via CLI:
```bash
# Save with encryption
kys secret_token "ghp_secure" --key "my-master-password"

# Retrieve with encryption
kyg secret_token --key "my-master-password"
```

#### Via Environment Variable:
```bash
export KYCLI_MASTER_KEY="my-master-password"
kyg secret_token
```

> [!IMPORTANT]
> If you attempt to retrieve an encrypted key without the correct `master_key`, `kycli` will return a masked message: `[ENCRYPTED: Provide a master key to view this value]` instead of raw ciphertext.

### ⏳ Value-Level TTL (Time To Live)
Like Redis, you can set keys to expire automatically. `kycli` implements **Soft Expiration**: when a key hits its TTL, it is moved to the **Archive** table (not deleted) and can be recovered within 15 days using the `kyr` command.
```bash
# Expire in 60 seconds
kys temp_code "1234" --ttl 60

# Expire in 1 day
kys daily_report "data" --ttl 1d

# Expire in 1 month (30 days)
kys monthly_archive "data" --ttl 1M
```

---

### `kyg <key_or_regex>` — Search & Get
Retrieves a value. Supports exact matches and regex.
- **Auto-Deserialization**: If the value is a JSON object or list, it is automatically returned as a Python-friendly structure.
```bash
kyg username
# Result: maduru

kyg user_profile
# Result:
# {
#   "name": "balakrishna",
#   "role": "admin"
# }
```

### `kyf <query>` — Full-Text Search (FTS5)
Perform blazing-fast Google-like searches across your entire database. Powered by SQLite's FTS5 engine.
```bash
kyf "searching terms"
# Returns all keys and values where the terms appear.
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

### `kyc <key> [args...]` — Execute Mode
Run a stored value directly as a shell command.
- **Static Execution**: Run the command exactly as stored.
- **Dynamic Execution**: Pass additional arguments that get appended to the stored command.
```bash
# Store a command
kys list_files "ls -la"

# Execute it
kyc list_files

# Dynamic execution (appends /tmp)
kyc list_files /tmp
```

---

### `kyshell` — Interactive TUI Shell
Launch a multi-pane interactive shell to manage your data.
- **Auto-completion**: Tab-completion for all commands.
- **Split View**: Real-time audit trail in a separate pane as you execute commands.
- **Syntax Highlighting**: Beautifully formatted input and output.
```bash
kycli kyshell
```


### ⚙️ Global Configuration & Env Vars
`kycli` is highly configurable. You can change the database location, export formats, and UI themes via environment variables or configuration files.

#### 🌍 Environment Variables (Highest Priority)
The most direct way to configure `kycli` is via shell environment variables.

- **`KYCLI_DB_PATH`**: Overrides the default database location (`~/kydata.db`).
- **`KYCLI_MASTER_KEY`**: Sets the default master key for AES-256 encryption.
  ```bash
  export KYCLI_DB_PATH="/custom/path/to/database.db"
  export KYCLI_MASTER_KEY="your-secret-password"
  ```

#### 📁 Configuration Files
`kycli` looks for configuration in `.kyclirc` or `.kyclirc.json`.

**Example `.kyclirc` (JSON):**
```json
{
  "db_path": "~/.kydata.db",
  "export_format": "csv"
}
```

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

# 4. Encryption & TTL (Sync)
with Kycore(master_key="secret-pass") as kv:
    # Save with 10-minute expiration
    kv.save("temp_password", "123456", ttl="10m")
    
    # Save with 1-month expiration
    kv.save("persistent_secret", "data", ttl="1M")
    
    print(kv.getkey("temp_password")) # 123456
```

### 2. High-Throughput (Async)
Designed for `asyncio` applications like FastAPI.
```python
import asyncio
from kycli import Kycore

async def run_tasks():
    # Use encryption and TTL in async environments
    with Kycore(master_key="async-vault") as kv:
        await kv.save_async("session:active", "true", ttl=3600)
        current = await kv.getkey_async("session:active")
        print(f"Session active: {current}")

asyncio.run(run_tasks())
```

### 3. Schema Validation (Pydantic)
Enforce data integrity by attaching a Pydantic model to your store.
```python
from pydantic import BaseModel
from kycli import Kycore

class UserSchema(BaseModel):
    name: str
    age: int

# Initialize with schema validation
with Kycore(schema=UserSchema) as kv:
    # This will succeed and auto-serialize
    kv.save("user:101", {"name": "Balu", "age": 30})
    
    # This will raise a ValueError (Schema Validation Error)
    kv.save("user:102", {"name": "Invalid"}) 
```

### 4. Application / Class Integration
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

