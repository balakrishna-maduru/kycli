# cython: language_level=3
import os
import re
import csv
import json
import tempfile
import shutil
import asyncio
import base64
import time
import warnings
from datetime import datetime, timedelta, timezone
from collections import OrderedDict
try:
    from pydantic import BaseModel, ValidationError
except ImportError:
    BaseModel = None
    ValidationError = None

try:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except ImportError:
    AESGCM = None

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
    cdef object _aesgcm
    cdef str _master_key
    cdef object _cache
    cdef int _cache_limit

    def __init__(self, db_path=None, schema=None, master_key=None, cache_size=1000):
        """
        Initialize Kycore.
        :param db_path: Path to the SQLite database.
        :param schema: An optional Pydantic BaseModel for data validation.
        :param master_key: An optional master key for AES-256 encryption.
        :param cache_size: Size of the L1 LRU cache.
        """
        self._cache = OrderedDict()
        self._cache_limit = cache_size
        if schema and BaseModel and not issubclass(schema, BaseModel):
            raise TypeError("Schema must be a Pydantic BaseModel class")
        self._schema = schema
        self._master_key = master_key
        self._aesgcm = None

        if master_key:
            if AESGCM is None:
                raise ImportError("cryptography library is required for encryption. Install it with 'pip install cryptography'.")
            
            # Derive a 256-bit key from the master key
            # Using a fixed salt for simplicity in this implementation, 
            # though a per-DB salt would be better.
            salt = b'kycli_vault_salt' 
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=100000,
            )
            key = kdf.derive(master_key.encode('utf-8'))
            self._aesgcm = AESGCM(key)

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
                value TEXT,
                expires_at DATETIME
            )
        """)
        # Ensure expires_at column exists for older versions
        try:
            self._execute_raw("ALTER TABLE kvstore ADD COLUMN expires_at DATETIME")
        except:
            pass # Already exists

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

        # TTL Cleanup: Move expired keys to archive before deleting
        self._execute_raw("""
            INSERT INTO archive (key, value)
            SELECT key, value FROM kvstore 
            WHERE expires_at IS NOT NULL AND expires_at < datetime('now')
        """)
        self._execute_raw("DELETE FROM kvstore WHERE expires_at IS NOT NULL AND expires_at < datetime('now')")
        
        self._dirty_keys = set()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._db:
            sqlite3_close(self._db)
            self._db = NULL

    cdef str _encrypt_c(self, str plaintext):
        if self._aesgcm is None:
            return plaintext
        nonce = os.urandom(12)
        ciphertext = self._aesgcm.encrypt(nonce, plaintext.encode('utf-8'), None)
        return "enc:" + base64.b64encode(nonce + ciphertext).decode('utf-8')

    cdef str _decrypt_c(self, str encrypted_text):
        if encrypted_text is None:
            return "[DELETED]"
            
        if not encrypted_text.startswith("enc:"):
            return encrypted_text
            
        if self._aesgcm is None:
            return "[ENCRYPTED: Provide a master key to view this value]"
            
        try:
            data = base64.b64decode(encrypted_text[4:].encode('utf-8'))
            nonce = data[:12]
            ciphertext = data[12:]
            return self._aesgcm.decrypt(nonce, ciphertext, None).decode('utf-8')
        except Exception:
            return "[DECRYPTION FAILED: Incorrect master key]"

    def _encrypt(self, str plaintext):
        return self._encrypt_c(plaintext)

    def _decrypt(self, str encrypted_text):
        return self._decrypt_c(encrypted_text)

    cdef int _execute_raw(self, str sql) except -1:
        cdef bytes sql_bytes = sql.encode('utf-8')
        cdef char* errmsg = NULL
        if sqlite3_exec(self._db, sql_bytes, NULL, NULL, &errmsg) != SQLITE_OK:
            msg = errmsg.decode('utf-8') if errmsg else "Unknown error"
            raise RuntimeError(f"SQLite error: {msg}")
        return 0

    def _parse_ttl(self, ttl):
        if ttl is None:
            return None
        if isinstance(ttl, (int, float)):
            return int(ttl)
        
        cdef str s_ttl = str(ttl).strip()
        if not s_ttl:
            return None
        if s_ttl.isdigit():
            return int(s_ttl)
            
        match = re.match(r'^(\d+)([smhdwMy])$', s_ttl)
        if not match:
            try:
                return int(s_ttl)
            except ValueError:
                raise ValueError(f"Invalid TTL format: '{s_ttl}'. Use suffixes: s, m, h, d, w, M, y (e.g., 10m, 2h, 1d, 1M)")
        
        cdef long val = int(match.group(1))
        cdef str unit = match.group(2)
        
        if unit == 's': return val
        if unit == 'm': return val * 60
        if unit == 'h': return val * 3600
        if unit == 'd': return val * 86400
        if unit == 'w': return val * 604800
        if unit == 'M': return val * 2592000 # 30 days
        if unit == 'y': return val * 31536000 # 365 days
        return val

    def save(self, str key, value, ttl=None):
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

        # 3. Encryption
        cdef str storage_val = self._encrypt_c(string_val)

        cdef str existing = self.getkey(k, deserialize=False)
        
        if existing == string_val:
            return "nochange"
        
        status = "overwritten" if existing != "Key not found" else "created"

        cdef str expires_at = None
        if ttl:
            expires_at = (datetime.now(timezone.utc) + timedelta(seconds=self._parse_ttl(ttl))).strftime('%Y-%m-%d %H:%M:%S')

        try:
            self._execute_raw("BEGIN TRANSACTION")
            
            # Update kvstore
            self._bind_and_execute("INSERT OR REPLACE INTO kvstore (key, value, expires_at) VALUES (?, ?, ?)", [k, storage_val, expires_at])
            # Update audit log
            self._bind_and_execute("INSERT INTO audit_log (key, value) VALUES (?, ?)", [k, storage_val])
            
            self._execute_raw("COMMIT")
            self._dirty_keys.add(k)
            
            # Update L1 Cache
            self._cache[k] = value
            self._cache.move_to_end(k)
            if len(self._cache) > self._cache_limit:
                self._cache.popitem(last=False)
                
            return status
        except Exception as e:
            self._execute_raw("ROLLBACK")
            raise e

    def save_many(self, list items, ttl=None):
        """
        Batch save multiple key-value pairs in a single transaction.
        :param items: List of tuples (key, value)
        :param ttl: Optional global TTL for all items in the batch
        """
        if not items:
            return
            
        cdef str expires_at = None
        if ttl:
            expires_at = (datetime.now(timezone.utc) + timedelta(seconds=self._parse_ttl(ttl))).strftime('%Y-%m-%d %H:%M:%S')

        try:
            self._execute_raw("BEGIN TRANSACTION")
            
            for key, value in items:
                k = key.lower().strip()
                # Validation & Serialization
                if self._schema:
                    if isinstance(value, dict):
                        value = self._schema(**value).model_dump()
                
                if isinstance(value, (dict, list, bool, int, float)):
                    string_val = json.dumps(value)
                else:
                    string_val = str(value)
                
                storage_val = self._encrypt_c(string_val)
                
                self._bind_and_execute("INSERT OR REPLACE INTO kvstore (key, value, expires_at) VALUES (?, ?, ?)", [k, storage_val, expires_at])
                self._bind_and_execute("INSERT INTO audit_log (key, value) VALUES (?, ?)", [k, storage_val])
                
                # Update L1 Cache
                self._cache[k] = value
                self._cache.move_to_end(k)
                if len(self._cache) > self._cache_limit:
                    self._cache.popitem(last=False)
                    
            self._execute_raw("COMMIT")
        except Exception as e:
            self._execute_raw("ROLLBACK")
            raise e

    async def save_async(self, str key, value, ttl=None):
        """Asynchronous version of save using a thread pool."""
        return await asyncio.to_thread(self.save, key, value, ttl=ttl)

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
        cdef list results = self._bind_and_fetch("""
            SELECT 1 FROM kvstore 
            WHERE key = ? 
            AND (expires_at IS NULL OR expires_at > datetime('now'))
        """, [key.lower().strip()])
        return len(results) > 0

    def __iter__(self):
        results = self._bind_and_fetch("""
            SELECT key FROM kvstore 
            WHERE (expires_at IS NULL OR expires_at > datetime('now'))
        """, [])
        for row in results:
            yield row[0]

    def __len__(self):
        results = self._bind_and_fetch("""
            SELECT COUNT(*) FROM kvstore 
            WHERE (expires_at IS NULL OR expires_at > datetime('now'))
        """, [])
        return int(results[0][0]) if results else 0

    def getkey(self, str key_pattern, deserialize=True):
        cdef str k = key_pattern.lower().strip()
        
        # 1. Try exact match (including expired to handle notifications)
        # Fetch status using SQLite time for consistency
        cdef list results = self._bind_and_fetch("""
            SELECT value, expires_at, (expires_at < datetime('now')) as is_expired
            FROM kvstore 
            WHERE key = ?
        """, [k])
        
        cdef str raw_val
        cdef str exp_at
        cdef int is_expired
        if results:
            raw_val = results[0][0]
            exp_at = results[0][1]
            is_expired = int(results[0][2]) if results[0][2] is not None else 0
            
            # Check if expired
            if is_expired:
                warnings.warn(f"Key '{k}' expired at {exp_at} and has been moved to archive.", UserWarning)
                # Move to archive and delete
                self._execute_raw("BEGIN TRANSACTION")
                self._bind_and_execute("INSERT INTO archive (key, value) VALUES (?, ?)", [k, raw_val])
                self._bind_and_execute("DELETE FROM kvstore WHERE key = ?", [k])
                self._execute_raw("COMMIT")
                return "Key not found"
                
            # Check L1 Cache
            if k in self._cache:
                self._cache.move_to_end(k)
                return self._cache[k]

            raw_val = self._decrypt_c(raw_val)
            val = raw_val
            if deserialize:
                try:
                    val = json.loads(raw_val)
                except:
                    val = raw_val
            
            # Update L1 Cache
            self._cache[k] = val
            self._cache.move_to_end(k)
            if len(self._cache) > self._cache_limit:
                self._cache.popitem(last=False)
                
            return val

        # 2. Try regex
        results = self._bind_and_fetch("""
            SELECT key, value FROM kvstore 
            WHERE (expires_at IS NULL OR expires_at > datetime('now'))
        """, [])
        try:
            regex = re.compile(key_pattern, re.IGNORECASE)
        except re.error:
            return "Key not found"

        matches = {}
        for row in results:
            if regex.search(row[0]):
                decrypted_val = self._decrypt_c(row[1])
                if deserialize:
                    try:
                        matches[row[0]] = json.loads(decrypted_val)
                    except:
                        matches[row[0]] = decrypted_val
                else:
                    matches[row[0]] = decrypted_val
                    
        return matches if matches else "Key not found"

    def search(self, str query, limit=100, deserialize=True, keys_only=False):
        """
        Perform a high-performance full-text search using FTS5.
        
        :param query: The FTS5 search query.
        :param limit: Maximum number of results to return (default 100).
        :param deserialize: Whether to auto-parse JSON values (default True).
        :param keys_only: If True, only returns a list of keys (fastest).
        """
        cdef str sql
        if keys_only:
            sql = """
                SELECT kvstore.key FROM kvstore 
                JOIN fts_kvstore ON kvstore.rowid = fts_kvstore.rowid 
                WHERE fts_kvstore MATCH ? 
                AND (kvstore.expires_at IS NULL OR kvstore.expires_at > datetime('now'))
                ORDER BY rank
                LIMIT ?
            """
        else:
            sql = """
                SELECT kvstore.key, kvstore.value FROM kvstore 
                JOIN fts_kvstore ON kvstore.rowid = fts_kvstore.rowid 
                WHERE fts_kvstore MATCH ? 
                AND (kvstore.expires_at IS NULL OR kvstore.expires_at > datetime('now'))
                ORDER BY rank
                LIMIT ?
            """
        
        results = self._bind_and_fetch(sql, [query, limit])
        
        if keys_only:
            return [row[0] for row in results]

        matches = {}
        for row in results:
            decrypted_val = self._decrypt(row[1])
            if deserialize:
                try:
                    matches[row[0]] = json.loads(decrypted_val)
                except:
                    matches[row[0]] = decrypted_val
            else:
                matches[row[0]] = decrypted_val
        return matches

    def optimize_index(self):
        """Optimize the FTS5 index for faster search performance."""
        self._execute_raw("INSERT INTO fts_kvstore(fts_kvstore) VALUES('optimize')")

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
            
        cdef str val = results[0][0] # Keep encrypted in archive
        
        try:
            self._execute_raw("BEGIN TRANSACTION")
            # Move to archive
            self._bind_and_execute("INSERT INTO archive (key, value) VALUES (?, ?)", [k, val])
            # Record deletion in audit log for PITR
            self._bind_and_execute("INSERT INTO audit_log (key, value) VALUES (?, NULL)", [k])
            # Remove from active store
            self._bind_and_execute("DELETE FROM kvstore WHERE key=?", [k])
            self._execute_raw("COMMIT")
            
            self._dirty_keys.add(k)
            
            # Invalidate L1 Cache
            if k in self._cache:
                del self._cache[k]
                
            return "Deleted and moved to archive (Auto-permanently deleted after 15 days)"
        except Exception as e:
            self._execute_raw("ROLLBACK")
            raise e

    def get_replication_stream(self, last_id=0):
        """
        Stream updates since a specific audit log ID for replication.
        """
        return self._bind_and_fetch("SELECT id, key, value, timestamp FROM audit_log WHERE id > ? ORDER BY id ASC", [last_id])

    def sync_from_stream(self, list entries):
        """
        Apply replication entries from another instance.
        """
        try:
            self._execute_raw("BEGIN TRANSACTION")
            for entry in entries:
                # entry is [id, key, value, timestamp]
                k, v = entry[1], entry[2]
                self._bind_and_execute("INSERT OR REPLACE INTO kvstore (key, value) VALUES (?, ?)", [k, v])
                # We don't add to audit_log to avoid loops, but we might want a 'sync' flag
            self._execute_raw("COMMIT")
        except Exception as e:
            self._execute_raw("ROLLBACK")
            raise e

    def restore_to(self, str timestamp):
        """
        Point-in-Time Recovery: Reconstruct database state at a specific timestamp.
        :param timestamp: Target timestamp (e.g., '2026-01-01 12:00:00')
        """
        try:
            self._execute_raw("BEGIN TRANSACTION")
            
            # 1. Clear current store
            self._execute_raw("DELETE FROM kvstore")
            
            # 2. Find latest non-NULL entry for each key before timestamp
            # We use a subquery to find the MAX(id) for each key up to the timestamp
            sql = """
                INSERT INTO kvstore (key, value)
                SELECT key, value FROM audit_log
                WHERE id IN (
                    SELECT MAX(id) FROM audit_log 
                    WHERE timestamp <= ? 
                    GROUP BY key
                ) AND value IS NOT NULL
            """
            self._bind_and_execute(sql, [timestamp])
            
            self._execute_raw("COMMIT")
            
            # 3. Invalidate cache
            self._cache.clear()
            
            return f"Database restored to state at {timestamp}"
        except Exception as e:
            self._execute_raw("ROLLBACK")
            raise e

    def compact(self, int retention_days=15):
        """
        Database Compaction: Cleanup old audit/archive data and reclaim space.
        :param retention_days: Number of days of history to keep (default 15)
        """
        try:
            # 1. Cleanup Audit Log
            self._bind_and_execute("DELETE FROM audit_log WHERE (julianday('now') - julianday(timestamp)) > ?", [retention_days])
            
            # 2. Cleanup Archive
            self._bind_and_execute("DELETE FROM archive WHERE (julianday('now') - julianday(deleted_at)) > ?", [retention_days])
            
            # 3. SQLite Maintenance
            self._execute_raw("VACUUM")
            self._execute_raw("ANALYZE")
            
            return "Compaction complete: Space reclaimed and stale history purged."
        except Exception as e:
            raise RuntimeError(f"Compaction failed: {e}")

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
            
        # Re-save it (latest_value is already encrypted if encryption was on)
        self._execute_raw("BEGIN TRANSACTION")
        self._bind_and_execute("INSERT OR REPLACE INTO kvstore (key, value) VALUES (?, ?)", [k, latest_value])
        self._bind_and_execute("INSERT INTO audit_log (key, value) VALUES (?, ?)", [k, latest_value])
        self._execute_raw("COMMIT")
        return f"Restored: {k}"

    def listkeys(self, pattern=None):
        results = self._bind_and_fetch("""
            SELECT key FROM kvstore 
            WHERE (expires_at IS NULL OR expires_at > datetime('now'))
        """, [])
        keys = [row[0] for row in results]
        if not pattern:
            return keys
        
        try:
            regex = re.compile(pattern, re.IGNORECASE)
            return [k for k in keys if regex.search(k)]
        except re.error:
            return []

    def get_history(self, str key=None):
        cdef list results
        if key is None or key == "-h":
            results = self._bind_and_fetch("SELECT key, value, timestamp FROM audit_log ORDER BY timestamp DESC, id DESC", [])
        else:
            results = self._bind_and_fetch("SELECT key, value, timestamp FROM audit_log WHERE key = ? ORDER BY timestamp DESC, id DESC", [key.lower().strip()])
        
        cdef list decrypted_results = []
        for row in results:
            decrypted_results.append([row[0], self._decrypt(row[1]), row[2]])
        return decrypted_results

    @property
    def store(self):
        results = self._bind_and_fetch("""
            SELECT key, value FROM kvstore 
            WHERE (expires_at IS NULL OR expires_at > datetime('now'))
        """, [])
        return {row[0]: self._decrypt(row[1]) for row in results}

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