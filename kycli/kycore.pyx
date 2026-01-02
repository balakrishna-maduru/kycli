# cython: language_level=3
from libc.string cimport strdup
import os
import sqlite3

cdef class Kycore:
    cdef object _conn
    cdef str _data_path
    cdef set _dirty_keys

    def __init__(self, db_path=None):
        """
        Initialize the Kycore storage instance.
        
        Args:
            db_path (str, optional): Path to the SQLite database. Defaults to ~/kydata.db.
        """
        if db_path is None:
            self._data_path = os.path.expanduser("~/kydata.db")
        else:
            self._data_path = db_path
            
        dir_name = os.path.dirname(self._data_path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)

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

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._conn:
            self._conn.close()

    @property
    def data_path(self):
        """Returns the absolute path to the database file."""
        return self._data_path

    def save(self, str key, str value):
        """
        Save a key-value pair to the store.
        
        Args:
            key (str): The unique identifier.
            value (str): The value to store.
            
        Returns:
            str: "created", "overwritten", or "nochange".
        """
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

    def __setitem__(self, str key, str value):
        self.save(key, value)

    def __getitem__(self, str key):
        val = self.getkey(key)
        if val == "Key not found":
            raise KeyError(key)
        return val

    def __delitem__(self, str key):
        res = self.delete(key)
        if res == "Key not found":
            raise KeyError(key)

    def __contains__(self, str key):
        cursor = self._conn.execute("SELECT 1 FROM kvstore WHERE key = ?", (key.lower(),))
        return cursor.fetchone() is not None

    def __iter__(self):
        cursor = self._conn.execute("SELECT key FROM kvstore")
        for row in cursor:
            yield row[0]

    def __len__(self):
        cursor = self._conn.execute("SELECT COUNT(*) FROM kvstore")
        return cursor.fetchone()[0]

    def get_history(self, str key=None):
        """
        Retrieve change history for a specific key or all keys.
        
        Args:
            key (str, optional): Key to filter history. Defaults to None (all keys).
            
        Returns:
            list: List of (key, value, timestamp) tuples.
        """
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
        """
        List all keys or those matching a regex pattern.
        
        Args:
            pattern (str, optional): Regex pattern to filter keys.
            
        Returns:
            list: List of keys.
        """
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
        """
        Get value for a key or multiple values for a regex pattern.
        
        Args:
            key_pattern (str): Exact key or regex pattern.
            
        Returns:
            str or dict: Value if exact match, dict of matches if regex, or error message.
        """
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
        """
        Delete a key from the store.
        
        Args:
            key (str): Key to delete.
            
        Returns:
            str: "Deleted" or "Key not found".
        """
        cursor = self._conn.execute("DELETE FROM kvstore WHERE key=?", (key.lower(),))
        self._conn.commit()
        if cursor.rowcount > 0:
            self._dirty_keys.add(key.lower())
            return "Deleted"
        return "Key not found"

    @property
    def store(self):
        """Returns the entire store as a dictionary."""
        cursor = self._conn.execute("SELECT key, value FROM kvstore")
        return dict(cursor.fetchall())

    def load_store(self, dict store_data):
        """Bulk load key-value pairs."""
        for k, v in store_data.items():
            self._conn.execute("INSERT OR REPLACE INTO kvstore (key, value) VALUES (?, ?)", (k.lower(), v))
        self._conn.commit()

    def persist(self):
        """Persist changes to disk (effectively a no-op as SQLite commits are immediate)."""
        self._dirty_keys.clear()

    cdef void _load(self):
        pass

    def export_data(self, str filepath, str file_format="csv"):
        """
        Export data to CSV or JSON.
        
        Args:
            filepath (str): Target file path.
            file_format (str): "csv" or "json".
        """
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
        """
        Import data from CSV or JSON.
        
        Args:
            filepath (str): Source file path.
        """
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