# 🔑 kycli — A Simple CLI Key-Value Store

`kycli` is a lightweight Python CLI utility to save, get, list, and delete key-value pairs directly from your terminal.

---

## 📦 Installation

```bash
pip install kycli
```
Or, clone and install locally:
```bash
git clone https://github.com/yourname/kycli.git
cd kycli
poetry install
```

🚀 Usage

You can access the CLI using the following commands:

✅ Save a value
```bash
kys <key> <value>
```
Example:
```bash
kys my_key "Hello, World!"
```
Output:
```
Saved: my_key
```

📥 Get a value
```bash
kyg <key>
```
Example:
```bash
kyg my_key
```
Output:
```
Hello, World!
```
```bash
kyg "my.*"
```
Output:
```
{
  "my_key": "Hello, World!"
}
```

📃 List all keys
```bash
kyl
```
Example:
```bash
kyl
```
Output:
```
Keys: my_key
```
```bash
kyl  "my_.*"
```
Output:
```
Keys: data
``` 

❌ Delete a key
```bash
kyd <key>
```
Example:
```bash
kyd my_key
```
Output:
``` bash
Deleted
```

ℹ️ Help
```bash
kyh
```
Example:
```bash
kyh
```
Output:
```
Available commands:
  kys <key> <value>     - Save key-value
  kyg <key>             - Get value by key
  kyl                   - List keys
  kyd <key>             - Delete key
  kyh                   - Help
  kye <file> [format]   - Export data to file (default CSV; JSON if specified)
  kyi <file>            - Import data (auto-detect CSV/JSON by file extension)
```

📂 Export
```bash
kye <file> [format]
```
Example:
```bash
kye data.csv
```
Output:
```
Exported to data.csv
```

📥 Import
```bash
kyi <file>
```
Example:
```bash
kyi data.csv
```
Output:
``` bash
Imported from data.csv
```

kyc

```bash
  kys myls "ls -la"
  kyc myls
```
Output:
```
Saved: myls
kyc myls                           
Executing: ls -la
total 96
drwxr-xr-x@ 15 user  staff    480 May 25 10:39 .
drwxr-xr-x  11 user  staff    352 May 18 19:58 ..
drwxr-xr-x  16 user  staff    512 May 25 10:48 .git
drwxr-xr-x   3 user  staff     96 May 18 21:37 .github
-rw-r--r--   1 user  staff    544 May 25 10:20 .gitignore
```
```bash
kys greet "echo Hello, {0}"
kyc greet "Krishna"
```
Output:
```
Saved: greet
Hello, Krishna
```



Author
---
👤 Balakrishna Maduru
- [GitHub](https://github.com/balakrishna-maduru)
- [LinkedIn](https://www.linkedin.com/in/balakrishna-maduru)
- [Twitter](https://x.com/krishonlyyou)