# cython: language_level=3
import os
import re
import csv
import json
import tempfile
import shutil
import asyncio
try:
    from pydantic import BaseModel, ValidationError
except ImportError:
    BaseModel = None
    ValidationError = None

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
    cdef object _schema

    def __init__(self, db_path=None, schema=None):
        """
        Initialize Kycore.
        :param db_path: Path to the SQLite database.
        :param schema: An optional Pydantic BaseModel for data validation.
        """
        if schema and BaseModel and not issubclass(schema, BaseModel):
            raise TypeError("Schema must be a Pydantic BaseModel class")
        self._schema = schema

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
        self._execute_raw("""
            CREATE TABLE IF NOT EXISTS archive (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT,
                value TEXT,
                deleted_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self._execute_raw("CREATE INDEX IF NOT EXISTS idx_audit_key ON audit_log(key)")
        
        # Initialize FTS5 for search
        self._execute_raw("CREATE VIRTUAL TABLE IF NOT EXISTS fts_kvstore USING fts5(key, value, content='kvstore')")
        self._execute_raw("""
            CREATE TRIGGER IF NOT EXISTS trg_kv_ai AFTER INSERT ON kvstore BEGIN
                INSERT INTO fts_kvstore(rowid, key, value) VALUES (new.rowid, new.key, new.value);
            END;
            CREATE TRIGGER IF NOT EXISTS trg_kv_ad AFTER DELETE ON kvstore BEGIN
                INSERT INTO fts_kvstore(fts_kvstore, rowid, key, value) VALUES('delete', old.rowid, old.key, old.value);
            END;
            CREATE TRIGGER IF NOT EXISTS trg_kv_au AFTER UPDATE ON kvstore BEGIN
                INSERT INTO fts_kvstore(fts_kvstore, rowid, key, value) VALUES('delete', old.rowid, old.key, old.value);
                INSERT INTO fts_kvstore(rowid, key, value) VALUES (new.rowid, new.key, new.value);
            END;
        """)

        # Auto-cleanup: Delete archived items older than 15 days
        self._execute_raw("DELETE FROM archive WHERE (julianday('now') - julianday(deleted_at)) > 15")
        
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

    def save(self, str key, value):
        if not key or not key.strip():
            raise ValueError("Key cannot be empty")
        if value is None:
            raise ValueError("Value cannot be None")
            
        cdef str k = key.lower().strip()
        cdef str string_val
        
        # 1. Pydantic Validation
        if self._schema:
            try:
                if isinstance(value, dict):
                    validated = self._schema(**value)
                    value = validated.model_dump()
                else:
                    # Try to parse if it's a string that might be JSON
                    if isinstance(value, str):
                        validated = self._schema.model_validate_json(value)
                        value = validated.model_dump()
            except ValidationError as e:
                raise ValueError(f"Schema Validation Error: {e}")

        # 2. Structured Serialization
        if isinstance(value, (dict, list, bool, int, float)):
            string_val = json.dumps(value)
        else:
            string_val = str(value)

        cdef str existing = self.getkey(k, deserialize=False)
        
        if existing == string_val:
            return "nochange"
        
        status = "overwritten" if existing != "Key not found" else "created"

        try:
            self._execute_raw("BEGIN TRANSACTION")
            
            # Update kvstore
            self._bind_and_execute("INSERT OR REPLACE INTO kvstore (key, value) VALUES (?, ?)", [k, string_val])
            # Update audit log
            self._bind_and_execute("INSERT INTO audit_log (key, value) VALUES (?, ?)", [k, string_val])
            
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

    def getkey(self, str key_pattern, deserialize=True):
        cdef str k = key_pattern.lower().strip()
        
        # 1. Try exact match
        cdef list results = self._bind_and_fetch("SELECT value FROM kvstore WHERE key = ?", [k])
        cdef str raw_val
        if results:
            raw_val = results[0][0]
            if deserialize:
                try:
                    return json.loads(raw_val)
                except:
                    return raw_val
            return raw_val

        # 2. Try regex
        results = self._bind_and_fetch("SELECT key, value FROM kvstore", [])
        try:
            regex = re.compile(key_pattern, re.IGNORECASE)
        except re.error:
            return "Key not found"

        matches = {}
        for row in results:
            if regex.search(row[0]):
                if deserialize:
                    try:
                        matches[row[0]] = json.loads(row[1])
                    except:
                        matches[row[0]] = row[1]
                else:
                    matches[row[0]] = row[1]
                    
        return matches if matches else "Key not found"

    def search(self, str query, deserialize=True):
        """Perform a full-text search using FTS5."""
        results = self._bind_and_fetch("SELECT key, value FROM fts_kvstore WHERE fts_kvstore MATCH ?", [query])
        matches = {}
        for row in results:
            if deserialize:
                try:
                    matches[row[0]] = json.loads(row[1])
                except:
                    matches[row[0]] = row[1]
            else:
                matches[row[0]] = row[1]
        return matches

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
        
        # Fetch value before deleting to move it to archive
        cdef list results = self._bind_and_fetch("SELECT value FROM kvstore WHERE key = ?", [k])
        if not results:
            return "Key not found"
            
        cdef str val = results[0][0]
        
        try:
            self._execute_raw("BEGIN TRANSACTION")
            # Move to archive
            self._bind_and_execute("INSERT INTO archive (key, value) VALUES (?, ?)", [k, val])
            # Remove from active store
            self._bind_and_execute("DELETE FROM kvstore WHERE key=?", [k])
            self._execute_raw("COMMIT")
            
            self._dirty_keys.add(k)
            return "Deleted and moved to archive (Auto-permanently deleted after 15 days)"
        except Exception as e:
            self._execute_raw("ROLLBACK")
            raise e

    def restore(self, str key):
        """Restore the latest value for a key from the archive."""
        cdef str k = key.lower().strip()
        
        # Pull latest from archive
        cdef list results = self._bind_and_fetch("SELECT value FROM archive WHERE key = ? ORDER BY deleted_at DESC LIMIT 1", [k])
        
        if not results:
            return "No archived version found for this key (Note: Archive is purged after 15 days)"
            
        cdef str latest_value = results[0][0]
        
        # Check if it's already in kvstore (maybe it was recreated)
        results = self._bind_and_fetch("SELECT value FROM kvstore WHERE key = ?", [k])
        if results and results[0][0] == latest_value:
            return "Already in active store with identical value"
            
        # Re-save it to kvstore and audit log
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