# 🔑 kycli — A Robust CLI Key-Value Store

`kycli` is a lightweight, high-performance Python CLI utility to save, get, list, and audit key-value pairs directly from your terminal. Built with Cython and SQLite for speed and reliability.

---

## 📦 Installation

```bash
pip install kycli
```
Or, clone and install locally:
```bash
git clone https://github.com/balakrishna-maduru/kycli.git
cd kycli
python3 -m pip install -e .
```

🚀 Usage
--

### ✅ Save a value
```bash
kys <key> <value>
```
**Safety Features:**
*   Automatically normalizes keys to lowercase and trims whitespace.
*   **Overwrite Protection:** Asks for confirmation (Y/N) if the key already exists with a different value.
*   **Integrity:** Prevents saving empty keys or values.

### 📥 Get current value
```bash
kyg <key>
```
*   Supports exact key matching.
*   Supports **Regex** patterns (e.g., `kyg "user_.*"`).

### 📜 Audit & History
```bash
kyv           # View full audit history (no arguments)
kyv -h        # View full audit history (identical to kyv)
kyv <key>     # View the latest historical value for a specific key
```
*   Every change is timestamped and logged in an audit trail.

### 📃 List Keys
```bash
kyl           # List all keys
kyl "pattern" # List keys matching a regex
```

### ❌ Delete
```bash
kyd <key>
```

### 📂 Portability
```bash
kye data.csv          # Export to CSV (default)
kye data.json json    # Export to JSON
kyi backup.csv        # Import from file (auto-detects format)
```
*   **Atomic Exports:** Uses temporary files and atomic moves to ensure your exports are never corrupted during a crash.

---
## 🛠 Advanced Features
*   **Concurrency Support:** Built-in retry mechanism for SQLite database locks.
*   **Persistence:** Data is stored in `~/kydata.db`.
*   **Speed:** Core logic is compiled with **Cython** for maximum throughput.

Author
---
👤 Balakrishna Maduru
- [GitHub](https://github.com/balakrishna-maduru)
- [LinkedIn](https://www.linkedin.com/in/balakrishna-maduru)
- [Twitter](https://x.com/krishonlyyou)