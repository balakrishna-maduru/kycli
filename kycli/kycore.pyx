# cython: language_level=3
from libc.string cimport strdup
import os
import sqlite3
import re
import json
import csv

cdef class Kycore:
    cdef object _conn
    cdef str _data_path
    cdef set _dirty_keys # This looks like a potentially unused attribute

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
        self._dirty_keys = set() # Consider removing if not used for persistence/caching

    @property
    def data_path(self):
        return self._data_path

    def save(self, str key, str value):
        key = key.lower()
        self._conn.execute("INSERT OR REPLACE INTO kvstore (key, value) VALUES (?, ?)", (key, value))
        self._conn.commit()
        # self._dirty_keys.add(key) # Remove if not used for specific caching/sync

    def listkeys(self, pattern: str = None):
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
        # First, try exact match for performance
        cursor = self._conn.execute("SELECT value FROM kvstore WHERE key=?", (key_pattern.lower(),))
        exact_match = cursor.fetchone()
        if exact_match:
            return exact_match[0]

        # If no exact match, try regex search over all keys
        cursor = self._conn.execute("SELECT key, value FROM kvstore")
        rows = cursor.fetchall()

        try:
            regex = re.compile(key_pattern, re.IGNORECASE)
        except re.error:
            return "Invalid regex"

        matches = {k: v for k, v in rows if regex.search(k)}
        # Return the exact value if only one regex match, otherwise return the dict of matches
        if len(matches) == 1:
            return list(matches.values())[0]
        return matches if matches else "Key not found"


    def delete(self, str key):
        cursor = self._conn.execute("DELETE FROM kvstore WHERE key=?", (key.lower(),))
        self._conn.commit()
        if cursor.rowcount > 0:
            # self._dirty_keys.add(key.lower()) # Remove if not used
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

    def export_data(self, str filepath, str file_format="csv"):
        data = self.store
        if file_format.lower() == "json":
            with open(filepath, "w") as f:
                json.dump(data, f, indent=4)
        else: # Default to CSV
            with open(filepath, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["key", "value"])
                for k, v in data.items():
                    writer.writerow([k, v])

    def import_data(self, str filepath):
        data = {}
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
        # self._dirty_keys.update(data.keys()) # Remove if not used