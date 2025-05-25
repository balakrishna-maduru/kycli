# cython: language_level=3
from libc.string cimport strdup
import os
import sqlite3

cdef class Kycore:
    cdef object _conn
    cdef str _data_path
    cdef set _dirty_keys

    def __cinit__(self):
        self._data_path = os.path.expanduser("~/kydata.db")
        os.makedirs(os.path.dirname(self._data_path), exist_ok=True)

        self._conn = sqlite3.connect(self._data_path)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS kvstore (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        self._dirty_keys = set()

    @property
    def data_path(self):
        return self._data_path

    def save(self, str key, str value):
        key = key.lower()
        self._conn.execute("INSERT OR REPLACE INTO kvstore (key, value) VALUES (?, ?)", (key, value))
        self._conn.commit()
        self._dirty_keys.add(key)

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
        import csv, json
        data = self.store

        if file_format.lower() == "json":
            with open(filepath, "w") as f:
                json.dump(data, f, indent=4)
        else:
            with open(filepath, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["key", "value"])
                for k, v in data.items():
                    writer.writerow([k, v])

    def import_data(self, str filepath):
        import csv, json

        if filepath.endswith(".json"):
            with open(filepath, "r") as f:
                data = json.load(f)
        elif filepath.endswith(".csv"):
            with open(filepath, "r") as f:
                reader = csv.DictReader(f)
                data = {row["key"].lower(): row["value"] for row in reader}
        else:
            raise ValueError("Unsupported file format: " + filepath)

        self.load_store(data)
        self._dirty_keys.update(data.keys())