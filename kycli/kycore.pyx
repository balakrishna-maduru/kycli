# cython: language_level=3
import os
import re
import csv
import json
import tempfile
import shutil
import asyncio
# SQLite C API definitions
cdef extern from "sqlite3.h":
    ctypedef struct sqlite3:
        pass
    ctypedef struct sqlite3_stmt:
        pass

    int SQLITE_OK = 0
    int SQLITE_ROW = 100
    int SQLITE_DONE = 101
    
    ctypedef void (*sqlite3_destructor_type)(void*)
    sqlite3_destructor_type SQLITE_TRANSIENT = <sqlite3_destructor_type>-1

    int sqlite3_open(const char *filename, sqlite3 **ppDb)
    int sqlite3_close(sqlite3*)
    int sqlite3_prepare_v2(sqlite3 *db, const char *zSql, int nByte, sqlite3_stmt **ppStmt, const char **pzTail)
    int sqlite3_step(sqlite3_stmt*)
    int sqlite3_finalize(sqlite3_stmt*)
    int sqlite3_exec(sqlite3*, const char *sql, int (*callback)(void*,int,char**,char**), void*, char **errmsg)
    int sqlite3_bind_text(sqlite3_stmt*, int, const char*, int n, sqlite3_destructor_type)
    const unsigned char *sqlite3_column_text(sqlite3_stmt*, int iCol)
    int sqlite3_column_count(sqlite3_stmt *pStmt)
    const char *sqlite3_column_name(sqlite3_stmt*, int N)
    int sqlite3_changes(sqlite3*)
    const char *sqlite3_errmsg(sqlite3*)

cdef class Kycore:
    cdef sqlite3* _db
    cdef str _data_path
    cdef set _dirty_keys

    def __init__(self, db_path=None):
        if db_path is None:
            self._data_path = os.path.expanduser("~/kydata.db")
        else:
            self._data_path = db_path
            
        dir_name = os.path.dirname(self._data_path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)

        cdef bytes path_bytes = self._data_path.encode('utf-8')
        if sqlite3_open(path_bytes, &self._db) != SQLITE_OK:
            raise RuntimeError(f"Could not open database: {sqlite3_errmsg(self._db)}")

        # Initialize tables and speed optimizations
        self._execute_raw("PRAGMA journal_mode=WAL")
        self._execute_raw("PRAGMA synchronous=NORMAL")
        self._execute_raw("PRAGMA cache_size=-64000")
        self._execute_raw("PRAGMA temp_store=MEMORY")
        
        self._execute_raw("""
            CREATE TABLE IF NOT EXISTS kvstore (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        self._execute_raw("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT,
                value TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self._execute_raw("CREATE INDEX IF NOT EXISTS idx_audit_key ON audit_log(key)")
        
        self._dirty_keys = set()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._db:
            sqlite3_close(self._db)
            self._db = NULL

    cdef int _execute_raw(self, str sql) except -1:
        cdef bytes sql_bytes = sql.encode('utf-8')
        cdef char* errmsg = NULL
        if sqlite3_exec(self._db, sql_bytes, NULL, NULL, &errmsg) != SQLITE_OK:
            msg = errmsg.decode('utf-8') if errmsg else "Unknown error"
            raise RuntimeError(f"SQLite error: {msg}")
        return 0

    def save(self, str key, str value):
        if not key or not key.strip():
            raise ValueError("Key cannot be empty")
        if not value:
            raise ValueError("Value cannot be empty")
            
        cdef str k = key.lower().strip()
        cdef str existing = self.getkey(k)
        
        if existing == value:
            return "nochange"
        
        status = "overwritten" if existing != "Key not found" else "created"

        try:
            self._execute_raw("BEGIN TRANSACTION")
            
            # Update kvstore
            self._bind_and_execute("INSERT OR REPLACE INTO kvstore (key, value) VALUES (?, ?)", [k, value])
            # Update audit log
            self._bind_and_execute("INSERT INTO audit_log (key, value) VALUES (?, ?)", [k, value])
            
            self._execute_raw("COMMIT")
            self._dirty_keys.add(k)
            return status
        except Exception as e:
            self._execute_raw("ROLLBACK")
            raise e

    async def save_async(self, str key, str value):
        """Asynchronous version of save using a thread pool."""
        return await asyncio.to_thread(self.save, key, value)

    def __setitem__(self, str key, str value):
        self.save(key, value)

    def __getitem__(self, str key):
        val = self.getkey(key)
        if val == "Key not found" or isinstance(val, dict):
            raise KeyError(key)
        return val

    def __delitem__(self, str key):
        res = self.delete(key)
        if res == "Key not found":
            raise KeyError(key)

    def __contains__(self, str key):
        cdef list results = self._bind_and_fetch("SELECT 1 FROM kvstore WHERE key = ?", [key.lower().strip()])
        return len(results) > 0

    def __iter__(self):
        results = self._bind_and_fetch("SELECT key FROM kvstore", [])
        for row in results:
            yield row[0]

    def __len__(self):
        results = self._bind_and_fetch("SELECT COUNT(*) FROM kvstore", [])
        return int(results[0][0]) if results else 0

    def getkey(self, str key_pattern):
        cdef str k = key_pattern.lower().strip()
        
        # 1. Try exact match
        cdef list results = self._bind_and_fetch("SELECT value FROM kvstore WHERE key = ?", [k])
        if results:
            return results[0][0]

        # 2. Try regex
        results = self._bind_and_fetch("SELECT key, value FROM kvstore", [])
        try:
            regex = re.compile(key_pattern, re.IGNORECASE)
        except re.error:
            return "Key not found"

        matches = {row[0]: row[1] for row in results if regex.search(row[0])}
        return matches if matches else "Key not found"

    async def getkey_async(self, str key_pattern):
        """Asynchronous version of getkey."""
        return await asyncio.to_thread(self.getkey, key_pattern)

    cdef _bind_and_execute(self, str sql, list params):
        cdef sqlite3_stmt* stmt = NULL
        cdef bytes sql_bytes = sql.encode('utf-8')
        if sqlite3_prepare_v2(self._db, sql_bytes, -1, &stmt, NULL) != SQLITE_OK:
            raise RuntimeError(f"Prepare error: {sqlite3_errmsg(self._db)}")
        
        cdef bytes p_bytes
        for i, p in enumerate(params):
            p_bytes = str(p).encode('utf-8')
            sqlite3_bind_text(stmt, i + 1, p_bytes, len(p_bytes), SQLITE_TRANSIENT)
            
        if sqlite3_step(stmt) != SQLITE_DONE:
            err = sqlite3_errmsg(self._db)
            sqlite3_finalize(stmt)
            raise RuntimeError(f"Step error: {err}")
        
        sqlite3_finalize(stmt)

    cdef list _bind_and_fetch(self, str sql, list params):
        cdef sqlite3_stmt* stmt = NULL
        cdef bytes sql_bytes = sql.encode('utf-8')
        if sqlite3_prepare_v2(self._db, sql_bytes, -1, &stmt, NULL) != SQLITE_OK:
            raise RuntimeError(f"Prepare error: {sqlite3_errmsg(self._db)}")
        
        cdef bytes p_bytes
        for i, p in enumerate(params):
            p_bytes = str(p).encode('utf-8')
            sqlite3_bind_text(stmt, i + 1, p_bytes, len(p_bytes), SQLITE_TRANSIENT)
            
        cdef list rows = []
        cdef int col_count
        cdef list row
        cdef const unsigned char* text
        
        while sqlite3_step(stmt) == SQLITE_ROW:
            col_count = sqlite3_column_count(stmt)
            row = []
            for i in range(col_count):
                text = sqlite3_column_text(stmt, i)
                if text == NULL:
                    row.append(None)
                else:
                    row.append((<char*>text).decode('utf-8'))
            rows.append(row)
            
        sqlite3_finalize(stmt)
        return rows

    def delete(self, str key):
        cdef str k = key.lower().strip()
        self._bind_and_execute("DELETE FROM kvstore WHERE key=?", [k])
        if sqlite3_changes(self._db) > 0:
            self._dirty_keys.add(k)
            return "Deleted"
        return "Key not found"

    def restore(self, str key):
        """Restore the latest value for a key from the audit_log."""
        cdef str k = key.lower().strip()
        cdef list history = self.get_history(k)
        
        if not history:
            return "No history found for this key"
            
        # history is ordered by DESC timestamp, so index 0 is the latest
        cdef str latest_value = history[0][1]
        
        # Check if it's already in kvstore with the same value
        cdef str current = self.getkey(k)
        if current == latest_value:
            return "Already up to date"
            
        # Re-save it to kvstore and audit log (as a restoration event)
        self.save(k, latest_value)
        return f"Restored: {k} (Value: {latest_value})"

    def listkeys(self, pattern=None):
        results = self._bind_and_fetch("SELECT key FROM kvstore", [])
        keys = [row[0] for row in results]
        if not pattern:
            return keys
        
        try:
            regex = re.compile(pattern, re.IGNORECASE)
            return [k for k in keys if regex.search(k)]
        except re.error:
            return []

    def get_history(self, str key=None):
        if key is None or key == "-h":
            return self._bind_and_fetch("SELECT key, value, timestamp FROM audit_log ORDER BY timestamp DESC, id DESC", [])
        else:
            return self._bind_and_fetch("SELECT key, value, timestamp FROM audit_log WHERE key = ? ORDER BY timestamp DESC, id DESC", [key.lower().strip()])

    @property
    def store(self):
        results = self._bind_and_fetch("SELECT key, value FROM kvstore", [])
        return {row[0]: row[1] for row in results}

    def load_store(self, dict store_data):
        if not store_data:
            return
        try:
            self._execute_raw("BEGIN TRANSACTION")
            for k, v in store_data.items():
                self._bind_and_execute("INSERT OR REPLACE INTO kvstore (key, value) VALUES (?, ?)", [k.lower(), v])
                self._bind_and_execute("INSERT INTO audit_log (key, value) VALUES (?, ?)", [k.lower(), v])
            self._execute_raw("COMMIT")
        except Exception as e:
            self._execute_raw("ROLLBACK")
            raise e

    def export_data(self, str filepath, str file_format="csv"):
        data = self.store
        dir_name = os.path.dirname(os.path.abspath(filepath))
        if dir_name: os.makedirs(dir_name, exist_ok=True)
        
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
            shutil.move(temp_path, filepath)
        except Exception:
            if os.path.exists(temp_path): os.remove(temp_path)
            raise

    def import_data(self, str filepath):
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Import file not found: {filepath}")
        data = {}
        if filepath.endswith(".json"):
            with open(filepath, "r") as f: data = json.load(f)
        elif filepath.endswith(".csv"):
            with open(filepath, "r") as f:
                reader = csv.DictReader(f)
                data = {row["key"]: row["value"] for row in reader}
        self.load_store(data)

    def persist(self):
        self._dirty_keys.clear()

    @property
    def data_path(self):
        return self._data_path