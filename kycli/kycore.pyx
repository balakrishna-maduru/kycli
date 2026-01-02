# cython: language_level=3
from libc.string cimport strdup
import os
import sqlite3

cdef class Kycore:
    cdef object _conn
    cdef str _data_path
    cdef set _dirty_keys

    def __init__(self, db_path=None):
        if db_path is None:
            self._data_path = os.path.expanduser("~/kydata.db")
        else:
            self._data_path = db_path
            
        os.makedirs(os.path.dirname(self._data_path), exist_ok=True)

        try:
            self._conn = sqlite3.connect(self._data_path)
            # Main Store
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS kvstore (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
            # Audit History
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key TEXT,
                    value TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            self._conn.commit()
        except sqlite3.Error as e:
            print(f"Error connecting to database: {e}")
            raise

        self._dirty_keys = set()

    @property
    def data_path(self):
        return self._data_path

    def save(self, str key, str value):
        if not key or not key.strip():
            raise ValueError("Key cannot be empty")
        if not value:
            raise ValueError("Value cannot be empty")
            
        key = key.lower().strip()
        
        # Check if exists and if value is different
        cursor = self._conn.execute("SELECT value FROM kvstore WHERE key = ?", (key,))
        existing = cursor.fetchone()
        
        status = "created"
        if existing:
            if existing[0] == value:
                return "nochange"
            status = "overwritten"

        try:
            # 1. Update main store
            self._conn.execute("INSERT OR REPLACE INTO kvstore (key, value) VALUES (?, ?)", (key, value))
            
            # 2. Record in audit log
            self._conn.execute("INSERT INTO audit_log (key, value) VALUES (?, ?)", (key, value))
            
            self._conn.commit()
            self._dirty_keys.add(key)
            return status
        except sqlite3.Error as e:
            print(f"Error saving to database: {e}")
            raise

    def get_history(self, str key=None):
        if key is None or key == "-h":
            cursor = self._conn.execute("""
                SELECT key, value, timestamp FROM audit_log 
                ORDER BY timestamp DESC, id DESC
            """)
        else:
            key = key.lower().strip()
            cursor = self._conn.execute("""
                SELECT key, value, timestamp FROM audit_log 
                WHERE key = ? 
                ORDER BY timestamp DESC, id DESC
            """, (key,))
        return cursor.fetchall()

    def listkeys(self, pattern: str = None):
        import re
        cursor = self._conn.execute("SELECT key FROM kvstore")
        keys = [row[0] for row in cursor.fetchall()]

        if pattern:
            try:
                regex = re.compile(pattern, re.IGNORECASE)
                return [k for k in keys if regex.search(k)]
            except re.error:
                return []
        return keys

    def getkey(self, str key_pattern):
        import re
        cursor = self._conn.execute("SELECT key, value FROM kvstore")
        rows = cursor.fetchall()

        for k, v in rows:
            if k == key_pattern.lower():
                return v

        try:
            regex = re.compile(key_pattern, re.IGNORECASE)
        except re.error:
            return "Invalid regex"

        matches = {k: v for k, v in rows if regex.search(k)}
        return matches if matches else "Key not found"

    def delete(self, str key):
        cursor = self._conn.execute("DELETE FROM kvstore WHERE key=?", (key.lower(),))
        self._conn.commit()
        if cursor.rowcount > 0:
            self._dirty_keys.add(key.lower())
            return "Deleted"
        return "Key not found"

    @property
    def store(self):
        cursor = self._conn.execute("SELECT key, value FROM kvstore")
        return dict(cursor.fetchall())

    def load_store(self, dict store_data):
        for k, v in store_data.items():
            self._conn.execute("INSERT OR REPLACE INTO kvstore (key, value) VALUES (?, ?)", (k.lower(), v))
        self._conn.commit()

    def persist(self):
        # Nothing to do here anymore — data is always in SQLite
        self._dirty_keys.clear()

    cdef void _load(self):
        # No pickle to load, everything in SQLite
        pass

    def export_data(self, str filepath, str file_format="csv"):
        import csv, json, tempfile, shutil
        data = self.store
        
        # Create a temporary file in the same directory as target to ensure atomic rename
        dir_name = os.path.dirname(os.path.abspath(filepath))
        os.makedirs(dir_name, exist_ok=True)
        
        fd, temp_path = tempfile.mkstemp(dir=dir_name, prefix=".kycli_export_")
        try:
            with os.fdopen(fd, 'w', newline='') as f:
                if file_format.lower() == "json":
                    json.dump(data, f, indent=4)
                else:
                    writer = csv.writer(f)
                    writer.writerow(["key", "value"])
                    for k, v in data.items():
                        writer.writerow([k, v])
            
            # Atomic rename
            shutil.move(temp_path, filepath)
        except Exception:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise

    def import_data(self, str filepath):
        import csv, json
        import time

        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Import file not found: {filepath}")

        if filepath.endswith(".json"):
            with open(filepath, "r") as f:
                data = json.load(f)
        elif filepath.endswith(".csv"):
            with open(filepath, "r") as f:
                reader = csv.DictReader(f)
                data = {row["key"].lower(): row["value"] for row in reader}
        else:
            raise ValueError("Unsupported file format: " + filepath)

        # Retry logic for bulk import
        max_retries = 5
        for i in range(max_retries):
            try:
                self.load_store(data)
                break
            except sqlite3.OperationalError as e:
                if "database is locked" in str(e).lower() and i < max_retries - 1:
                    time.sleep(0.1 * (i + 1))
                    continue
                raise
        
        self._dirty_keys.update(data.keys())