# cython: language_level=3
from .sqlite_defs cimport *
from .engine cimport DatabaseEngine
from .security cimport SecurityManager
from .query cimport QueryEngine
from .audit cimport AuditManager

import os
import tempfile
import json
import re
import warnings
import asyncio
import shutil
import threading
import time
import contextlib
from datetime import datetime, timedelta, timezone
import tempfile
import uuid
import base64
import zlib
import struct
from collections import OrderedDict

cdef object _MISSING = object()

try:
    from pydantic import BaseModel, ValidationError
except ImportError:
    BaseModel = None
    ValidationError = None

try:
    import fcntl
    _HAVE_FLOCK = True
except ImportError:
    fcntl = None
    _HAVE_FLOCK = False
    warnings.warn(
        "kycli: fcntl unavailable (non-POSIX platform); cross-process write locking is "
        "disabled. Concurrent multi-process writes to the same workspace file are not "
        "mutually exclusive on this platform (atomic writes still prevent corruption).",
        RuntimeWarning,
    )


class _ProcessLock:
    """Sidecar advisory file lock (<db_path>.lock) guarding cross-process writes.

    fcntl.flock is kernel-managed: it releases automatically when every fd
    referring to the open file description closes, including on process
    crash/SIGKILL, so no stale-lock cleanup is required.
    """

    def __init__(self, lock_path, timeout=10.0):
        self._lock_path = lock_path
        self._timeout = timeout
        self._fh = None

    def acquire(self):
        if not _HAVE_FLOCK:
            return
        self._fh = open(self._lock_path, "a+b")
        deadline = time.monotonic() + self._timeout
        while True:
            try:
                fcntl.flock(self._fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                return
            except OSError:
                if time.monotonic() >= deadline:
                    self._fh.close()
                    self._fh = None
                    raise TimeoutError(
                        f"Could not acquire workspace lock within {self._timeout}s "
                        f"({self._lock_path}); another kycli process may be holding it."
                    )
                time.sleep(0.02)

    def release(self):
        if self._fh is not None:
            try:
                fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
            finally:
                self._fh.close()
                self._fh = None


cdef class Kycore:
    cdef DatabaseEngine _engine
    cdef SecurityManager _security
    cdef QueryEngine _query
    cdef AuditManager _audit
    cdef object _schema
    cdef object _cache
    cdef int _cache_limit
    cdef set _dirty_keys
    cdef str _real_db_path
    cdef str _lock_path
    cdef object _queue_lock
    cdef object _last_sync_fingerprint
    cdef bint _closed

    def __init__(self, db_path=None, schema=None, master_key=None, cache_size=1000):
        if db_path is None:
            db_path = os.path.expanduser("~/kydata.db")
        
        dir_name = os.path.dirname(db_path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)

        if master_key is None:
            master_key = os.environ.get("KYCLI_MASTER_KEY")

        self._real_db_path = db_path
        self._lock_path = db_path + ".lock"
        self._engine = DatabaseEngine(":memory:")
        self._security = SecurityManager(master_key)
        self._query = QueryEngine()
        self._audit = AuditManager(self._engine, self._security, self._query)

        self._cache = OrderedDict()
        self._cache_limit = cache_size
        self._schema = schema
        self._dirty_keys = set()
        self._queue_lock = threading.RLock()
        self._closed = False

        self._initialize_schema()

        # Load existing data if available
        if os.path.exists(self._real_db_path):
            self._load()

        self._expire_stale_keys()
        self._last_sync_fingerprint = self._file_fingerprint()

    def _expire_stale_keys(self):
        # TTL Cleanup: Move expired keys to archive before deleting
        self._engine._execute_raw("""
            INSERT INTO archive (key, value)
            SELECT key, value FROM kvstore
            WHERE expires_at IS NOT NULL AND expires_at < datetime('now')
        """)
        self._engine._execute_raw("DELETE FROM kvstore WHERE expires_at IS NOT NULL AND expires_at < datetime('now')")

    def _file_fingerprint(self):
        # (mtime_ns, size) pair used to detect whether a sibling process has
        # written to the workspace file since we last synced with it.
        try:
            st = os.stat(self._real_db_path)
            return (st.st_mtime_ns, st.st_size)
        except OSError:
            return None

    def _reload_locked(self):
        """Re-sync the in-memory engine with the latest persisted on-disk state.

        Must be called while holding the exclusive process lock so this
        process never overwrites a sibling process's already-persisted write.
        Skips the (relatively expensive) reload + cache flush when the
        on-disk file's fingerprint is unchanged since our last sync, which
        keeps back-to-back writes from the *same* process cheap and preserves
        the in-process LRU cache across them.
        """
        fingerprint = self._file_fingerprint()
        if fingerprint is not None and fingerprint == self._last_sync_fingerprint:
            return
        self._engine.close()
        self._engine = DatabaseEngine(":memory:")
        self._audit = AuditManager(self._engine, self._security, self._query)
        self._cache.clear()
        self._initialize_schema()
        if os.path.exists(self._real_db_path):
            self._load()
        self._expire_stale_keys()
        self._last_sync_fingerprint = self._file_fingerprint()

    @contextlib.contextmanager
    def _exclusive(self):
        """Cross-process write critical section: lock -> reload -> mutate -> persist -> unlock."""
        if self._closed:
            raise RuntimeError("Kycore instance is closed")
        lock = _ProcessLock(self._lock_path)
        lock.acquire()
        try:
            self._reload_locked()
            yield
            self._persist()
            self._last_sync_fingerprint = self._file_fingerprint()
        finally:
            lock.release()

    def _initialize_schema(self):
        # Initialize tables
        self._engine._execute_raw("""
            CREATE TABLE IF NOT EXISTS kvstore (
                key TEXT PRIMARY KEY,
                value TEXT,
                expires_at DATETIME
            )
        """)
        try:
            self._engine._execute_raw("ALTER TABLE kvstore ADD COLUMN expires_at DATETIME")
        except:
            pass

        self._engine._execute_raw("""
            CREATE TABLE IF NOT EXISTS workspace_meta (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

        self._engine._execute_raw("""
            CREATE TABLE IF NOT EXISTS queue_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                value TEXT,
                priority INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                available_at DATETIME,
                lease_until DATETIME,
                receipt_id TEXT,
                attempts INTEGER DEFAULT 0
            )
        """)
        try:
            self._engine._execute_raw("ALTER TABLE queue_items ADD COLUMN available_at DATETIME")
        except:
            pass
        try:
            self._engine._execute_raw("ALTER TABLE queue_items ADD COLUMN lease_until DATETIME")
        except:
            pass
        try:
            self._engine._execute_raw("ALTER TABLE queue_items ADD COLUMN receipt_id TEXT")
        except:
            pass
        try:
            self._engine._execute_raw("ALTER TABLE queue_items ADD COLUMN attempts INTEGER DEFAULT 0")
        except:
            pass
            
        self._engine._execute_raw("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT,
                value TEXT,
                timestamp DATETIME DEFAULT (STRFTIME('%Y-%m-%d %H:%M:%f', 'NOW'))
            )
        """)
        self._engine._execute_raw("""
            CREATE TABLE IF NOT EXISTS archive (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT,
                value TEXT,
                deleted_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self._engine._execute_raw("CREATE INDEX IF NOT EXISTS idx_audit_key ON audit_log(key)")
        
        # FTS5
        self._engine._execute_raw("CREATE VIRTUAL TABLE IF NOT EXISTS fts_kvstore USING fts5(key, value, content='kvstore')")
        self._engine._execute_raw("""
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
        self._engine._execute_raw("DELETE FROM archive WHERE (julianday('now') - julianday(deleted_at)) > 15")

    def _debug_sql(self, str sql):
        """Internal helper for testing."""
        self._engine._execute_raw(sql)

    def _debug_fetch(self, str sql, list params=None):
        """Internal helper for testing."""
        if params is None: params = []
        return self._engine._bind_and_fetch(sql, params)

    def __enter__(self):
        return self

    @property
    def data_path(self): return self._engine._data_path

    def __exit__(self, et, ev, tb):
        self._engine.close()
        self._closed = True

    def _encrypt(self, str val): return self._security.encrypt(val)
    def _decrypt(self, str val): return self._security.decrypt(val)

    def _compression_enabled(self):
        return self._get_workspace_setting("compression_enabled", "1") != "0"

    def _compression_threshold(self):
        value = self._get_workspace_setting("compression_threshold", "1024")
        try:
            return int(value)
        except Exception:
            return 1024

    def _encode_storage_value(self, value):
        if isinstance(value, (dict, list, bool, int, float)):
            string_val = json.dumps(value)
        else:
            string_val = str(value)
        if self._compression_enabled() and len(string_val.encode('utf-8')) >= self._compression_threshold():
            encoded = base64.b64encode(zlib.compress(string_val.encode('utf-8'))).decode('ascii')
            return "cmp:zlib:" + encoded, string_val
        return string_val, string_val

    def _decode_storage_value(self, val_str):
        if isinstance(val_str, str) and val_str.startswith("cmp:zlib:"):
            try:
                return zlib.decompress(base64.b64decode(val_str[9:].encode('ascii'))).decode('utf-8')
            except Exception:
                raise ValueError("Compressed value is corrupted")
        return val_str

    def _persist(self):
        # Dump DB to SQL
        cdef list sql_stmts = ["BEGIN TRANSACTION;"]
        
        # Dump KVStore
        rows = self._engine._bind_and_fetch("SELECT key, value, expires_at FROM kvstore", [])
        for r in rows:
            k, v, exp = r[0], r[1], r[2]
            exp_val = f"'{exp}'" if exp else "NULL"
            sql_stmts.append(f"INSERT OR REPLACE INTO kvstore (key, value, expires_at) VALUES ('{k.replace('\'', '\'\'')}', '{v.replace('\'', '\'\'')}', {exp_val});")
            
        # Dump Audit Log
        rows = self._engine._bind_and_fetch("SELECT key, value, timestamp FROM audit_log", [])
        for r in rows:
            k, v, ts = r[0], r[1], r[2]
            v_val = f"'{v.replace('\'', '\'\'')}'" if v else "NULL"
            sql_stmts.append(f"INSERT INTO audit_log (key, value, timestamp) VALUES ('{k.replace('\'', '\'\'')}', {v_val}, '{ts}');")
            
        # Dump Archive
        rows = self._engine._bind_and_fetch("SELECT key, value, deleted_at FROM archive", [])
        for r in rows:
            k, v, da = r[0], r[1], r[2]
            sql_stmts.append(f"INSERT INTO archive (key, value, deleted_at) VALUES ('{k.replace('\'', '\'\'')}', '{v.replace('\'', '\'\'')}', '{da}');")

        # Dump Workspace Meta
        rows = self._engine._bind_and_fetch("SELECT key, value FROM workspace_meta", [])
        for r in rows:
            k, v = r[0], r[1]
            v_val = f"'{v.replace('\'', '\'\'')}'" if v else "NULL"
            sql_stmts.append(f"INSERT OR REPLACE INTO workspace_meta (key, value) VALUES ('{k.replace('\'', '\'\'')}', {v_val});")

        # Dump Queue Items
        rows = self._engine._bind_and_fetch("SELECT id, value, priority, created_at, available_at, lease_until, receipt_id, attempts FROM queue_items ORDER BY id", [])
        for r in rows:
            q_id, v, prio, created_at, available_at, lease_until, receipt_id, attempts = r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7]
            v_val = f"'{v.replace('\'', '\'\'')}'" if v else "NULL"
            created_val = f"'{created_at}'" if created_at else "NULL"
            available_val = f"'{available_at}'" if available_at else "NULL"
            lease_val = f"'{lease_until}'" if lease_until else "NULL"
            receipt_val = f"'{receipt_id}'" if receipt_id else "NULL"
            sql_stmts.append(
                f"INSERT INTO queue_items (id, value, priority, created_at, available_at, lease_until, receipt_id, attempts) VALUES ({q_id}, {v_val}, {prio if prio is not None else 0}, {created_val}, {available_val}, {lease_val}, {receipt_val}, {attempts if attempts is not None else 0});"
            )
            
        sql_stmts.append("COMMIT;")
        full_sql = "\n".join(sql_stmts)

        # Compress & Encrypt
        compressed = zlib.compress(full_sql.encode('utf-8'))
        encrypted = self._security.encrypt_blob(compressed)

        # Write File: Header + EncryptedBlob (atomic temp-file + rename, never a
        # partial/torn write visible to a concurrent reader)
        header = b'KYCLI\x01'
        payload = header + encrypted
        dir_name = os.path.dirname(self._real_db_path) or "."
        fd, tmp_path = tempfile.mkstemp(prefix=".kycli_tmp_", dir=dir_name)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(payload)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, self._real_db_path)
        except Exception:
            try:
                os.remove(tmp_path)
            except OSError:
                pass
            raise

    def _load(self):
        try:
            with open(self._real_db_path, "rb") as f:
                data = f.read()
            
            if not data.startswith(b'KYCLI\x01'):
                # Legacy support? Or duplicate plain DB logic?
                # For now assumes manual migration or fresh start as per plan "Full Encryption"
                # But to be safe, if headers missing but looks like SQLite, maybe try to migrate?
                # Let's fail safe:
                if data[:15] == b'SQLite format 3':
                    raise ValueError("Legacy database format detected. Manual migration required.")
                raise ValueError("Invalid database format or corrupted file.")
                
            encrypted_blob = data[6:]
            compressed = self._security.decrypt_blob(encrypted_blob)
            sql = zlib.decompress(compressed).decode('utf-8')
            
            # Execute
            self._engine._execute_raw(sql)
            
        except Exception as e:
            # If load fails, we are in empty memory DB.
            # print(f"Warning: Failed to load database: {e}")
            raise e

    def _parse_ttl(self, ttl):
        if ttl is None: return None
        if isinstance(ttl, (int, float)): return int(ttl)
        s_ttl = str(ttl).strip()
        if not s_ttl: return None
        if s_ttl.isdigit(): return int(s_ttl)
        match = re.match(r'^(\d+)([smhdwMy])$', s_ttl)
        if not match:
            try: return int(s_ttl)
            except: raise ValueError(f"Invalid TTL format: '{s_ttl}'. Use suffixes: s, m, h, d, w, M, y (e.g., 10m, 2h, 1d, 1M)")
        val = int(match.group(1))
        unit = match.group(2)
        if unit == 's': return val
        if unit == 'm': return val * 60
        if unit == 'h': return val * 3600
        if unit == 'd': return val * 86400
        if unit == 'w': return val * 604800
        if unit == 'M': return val * 2592000
        if unit == 'y': return val * 31536000
        return val

    def _get_type(self):
        res = self._engine._bind_and_fetch("SELECT value FROM workspace_meta WHERE key='type'", [])
        if res and res[0][0]:
            return res[0][0]
        return "kv"

    def get_type(self):
        return self._get_type()

    def set_type(self, str type_name):
        if not type_name or not str(type_name).strip():
            raise ValueError("Workspace type is required")
        t = str(type_name).strip().lower()
        if t not in ("kv", "queue", "stack", "priority_queue"):
            raise ValueError(f"Invalid workspace type: {type_name}")

        with self._exclusive():
            existing = self._engine._bind_and_fetch("SELECT value FROM workspace_meta WHERE key='type'", [])
            if existing:
                if existing[0][0] != t:
                    raise ValueError("Workspace type already set and cannot be changed")
                return existing[0][0]

            self._engine._bind_and_execute("INSERT OR REPLACE INTO workspace_meta (key, value) VALUES (?, ?)", ["type", t])
            return t

    def _ensure_kv(self, str op_name):
        if self._get_type() != "kv":
            raise TypeError(f"'{op_name}' not supported on this workspace type")

    def _ensure_queue(self, str op_name):
        if self._get_type() == "kv":
            raise TypeError(f"'{op_name}' not supported")

    def _queue_order(self):
        wtype = self._get_type()
        if wtype == "queue":
            return "id ASC"
        if wtype == "stack":
            return "id DESC"
        if wtype == "priority_queue":
            return "priority DESC, id ASC"
        return None

    def _queue_where_clause(self):
        return "(available_at IS NULL OR julianday(available_at) <= julianday('now')) AND (lease_until IS NULL OR julianday(lease_until) <= julianday('now'))"

    def _get_workspace_setting(self, str key, default=None):
        res = self._engine._bind_and_fetch("SELECT value FROM workspace_meta WHERE key = ?", [key])
        if res and res[0][0] is not None:
            return res[0][0]
        return default

    def _set_workspace_setting(self, str key, value):
        val = None if value is None else str(value)
        with self._exclusive():
            self._engine._bind_and_execute("INSERT OR REPLACE INTO workspace_meta (key, value) VALUES (?, ?)", [key, val])
            return val

    def _ensure_write_allowed(self, access_key=None):
        readonly = self._get_workspace_setting("readonly", "0")
        if readonly == "1":
            raise PermissionError("Workspace is read-only")
        required_key = self._get_workspace_setting("access_key", None)
        effective_key = access_key if access_key is not None else os.environ.get("KYCLI_ACCESS_KEY")
        if required_key and required_key != effective_key:
            raise PermissionError("Workspace access key required")

    def set_default_ttl(self, ttl):
        parsed = self._parse_ttl(ttl) if ttl is not None else None
        self._set_workspace_setting("default_ttl", parsed)
        return parsed

    def get_default_ttl(self):
        value = self._get_workspace_setting("default_ttl", None)
        return int(value) if value not in (None, "") else None

    def set_read_only(self, enabled):
        self._set_workspace_setting("readonly", "1" if enabled else "0")
        return enabled

    def get_read_only(self):
        return self._get_workspace_setting("readonly", "0") == "1"

    def set_access_key(self, str access_key=None):
        self._set_workspace_setting("access_key", access_key)
        return access_key

    def get_access_key(self):
        return self._get_workspace_setting("access_key", None)

    def _queue_deserialize(self, str val, bint deserialize=True):
        val_str = self._decode_storage_value(self._security.decrypt(val))
        if not deserialize:
            return val_str
        try:
            return json.loads(val_str)
        except:
            return val_str

    def peek(self, bint deserialize=True):
        self._ensure_queue("peek")
        order_by = self._queue_order()
        if order_by is None:
            raise TypeError("'peek' not supported")
        with self._queue_lock:
            rows = self._engine._bind_and_fetch(f"SELECT value FROM queue_items WHERE {self._queue_where_clause()} ORDER BY {order_by} LIMIT 1", [])
        if not rows:
            return None
        return self._queue_deserialize(rows[0][0], deserialize)

    def pop(self, bint deserialize=True, count=1, lease=None):
        batch_size = int(count) if count else 1
        if batch_size < 1:
            raise ValueError("count must be >= 1")
        lease_seconds = self._parse_ttl(lease) if lease else None
        results = []
        with self._exclusive():
            self._ensure_queue("pop")
            order_by = self._queue_order()
            if order_by is None:
                raise TypeError("'pop' not supported")
            with self._queue_lock:
                try:
                    self._engine._execute_raw("BEGIN IMMEDIATE")
                    rows = self._engine._bind_and_fetch(
                        f"SELECT id, value FROM queue_items WHERE {self._queue_where_clause()} ORDER BY {order_by} LIMIT ?",
                        [batch_size],
                    )
                    if not rows:
                        self._engine._execute_raw("COMMIT")
                        return None
                    for row in rows:
                        row_id, val = row[0], row[1]
                        if lease_seconds:
                            receipt_id = str(uuid.uuid4())
                            lease_until = (datetime.now(timezone.utc) + timedelta(seconds=lease_seconds)).strftime('%Y-%m-%d %H:%M:%S.%f')
                            self._engine._bind_and_execute(
                                "UPDATE queue_items SET lease_until = ?, receipt_id = ?, attempts = attempts + 1 WHERE id = ?",
                                [lease_until, receipt_id, row_id]
                            )
                            results.append({"receipt_id": receipt_id, "value": self._queue_deserialize(val, deserialize)})
                        else:
                            self._engine._bind_and_execute("DELETE FROM queue_items WHERE id = ?", [row_id])
                            results.append(self._queue_deserialize(val, deserialize))
                    self._engine._execute_raw("COMMIT")
                    if batch_size == 1:
                        return results[0]
                    return results
                except Exception as e:
                    try:
                        self._engine._execute_raw("ROLLBACK")
                    except:
                        pass
                    raise e

    def ack(self, str receipt_id):
        with self._exclusive():
            self._ensure_queue("ack")
            self._ensure_write_allowed()
            with self._queue_lock:
                self._engine._execute_raw("BEGIN IMMEDIATE")
                rows = self._engine._bind_and_fetch("SELECT id FROM queue_items WHERE receipt_id = ?", [receipt_id])
                if not rows:
                    self._engine._execute_raw("COMMIT")
                    return "Receipt not found"
                self._engine._bind_and_execute("DELETE FROM queue_items WHERE receipt_id = ?", [receipt_id])
                self._engine._execute_raw("COMMIT")
                return "acked"

    def nack(self, str receipt_id, delay=None):
        delay_seconds = self._parse_ttl(delay) if delay else None
        available_at = None
        if delay_seconds:
            available_at = (datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)).strftime('%Y-%m-%d %H:%M:%S.%f')
        with self._exclusive():
            self._ensure_queue("nack")
            self._ensure_write_allowed()
            with self._queue_lock:
                self._engine._execute_raw("BEGIN IMMEDIATE")
                rows = self._engine._bind_and_fetch("SELECT id FROM queue_items WHERE receipt_id = ?", [receipt_id])
                if not rows:
                    self._engine._execute_raw("COMMIT")
                    return "Receipt not found"
                self._engine._bind_and_execute(
                    "UPDATE queue_items SET lease_until = NULL, receipt_id = NULL, available_at = ? WHERE receipt_id = ?",
                    [available_at, receipt_id]
                )
                self._engine._execute_raw("COMMIT")
                return "nacked"

    def count(self):
        self._ensure_queue("count")
        with self._queue_lock:
            res = self._engine._bind_and_fetch("SELECT COUNT(*) FROM queue_items", [])
            return int(res[0][0]) if res else 0

    def clear(self):
        with self._exclusive():
            self._ensure_queue("clear")
            with self._queue_lock:
                try:
                    self._engine._execute_raw("BEGIN IMMEDIATE")
                    self._engine._execute_raw("DELETE FROM queue_items")
                    self._engine._execute_raw("COMMIT")
                    return "cleared"
                except Exception as e:
                    try:
                        self._engine._execute_raw("ROLLBACK")
                    except:
                        pass
                    raise e

    def save(self, str key, value, ttl=None):
        if not key or not key.strip(): raise ValueError("Empty key")
        k = key.lower().strip()

        if self._schema:
            try:
                if isinstance(value, dict):
                    value = self._schema(**value).model_dump()
                elif isinstance(value, str):
                    value = self._schema.model_validate_json(value).model_dump()
            except ValidationError as e:
                raise ValueError(f"Schema Error: {e}")

        with self._exclusive():
            return self._save_locked(k, value, ttl)

    def _save_locked(self, str k, value, ttl=None):
        # Assumes the caller already holds self._exclusive() and has reloaded
        # the freshest on-disk state into self._engine.
        self._ensure_kv("kys")
        self._ensure_write_allowed()
        if ttl is None:
            ttl = self.get_default_ttl()

        storage_payload, string_val = self._encode_storage_value(value)
        storage_val = self._security.encrypt(string_val)
        if storage_payload != string_val:
            storage_val = self._security.encrypt(storage_payload)
        expires_at = None
        if ttl:
            expires_at = (datetime.now(timezone.utc) + timedelta(seconds=self._parse_ttl(ttl))).strftime('%Y-%m-%d %H:%M:%S.%f')

        existing = self.getkey(k, deserialize=False)
        if existing == string_val: return "nochange"
        status = "overwritten" if existing != "Key not found" else "created"

        try:
            self._engine._execute_raw("BEGIN TRANSACTION")
            self._engine._bind_and_execute("INSERT OR REPLACE INTO kvstore (key, value, expires_at) VALUES (?, ?, ?)", [k, storage_val, expires_at])
            self._engine._bind_and_execute("INSERT INTO audit_log (key, value) VALUES (?, ?)", [k, storage_val])
            self._engine._execute_raw("COMMIT")

            self._cache[k] = (value, expires_at)
            self._cache.move_to_end(k)
            if len(self._cache) > self._cache_limit: self._cache.popitem(last=False)
            return status
        except Exception as e:
            try:
                self._engine._execute_raw("ROLLBACK")
            except:
                pass
            raise RuntimeError(f"Save operation failed: {e}")

    def save_many(self, list items, ttl=None):
        if not items: return 0
        with self._exclusive():
            self._ensure_kv("kys")
            self._ensure_write_allowed()
            ttl_eff = ttl
            if ttl_eff is None:
                ttl_eff = self.get_default_ttl()
            exp_at = None
            if ttl_eff:
                exp_at = (datetime.now(timezone.utc) + timedelta(seconds=self._parse_ttl(ttl_eff))).strftime('%Y-%m-%d %H:%M:%S.%f')
            try:
                self._engine._execute_raw("BEGIN TRANSACTION")
                for key, val in items:
                    k = key.lower().strip()
                    if self._schema and isinstance(val, dict): val = self._schema(**val).model_dump()
                    storage_payload, _ = self._encode_storage_value(val)
                    st_val = self._security.encrypt(storage_payload)
                    self._engine._bind_and_execute("INSERT OR REPLACE INTO kvstore (key, value, expires_at) VALUES (?, ?, ?)", [k, st_val, exp_at])
                    self._engine._bind_and_execute("INSERT INTO audit_log (key, value) VALUES (?, ?)", [k, st_val])
                    self._cache[k] = (val, exp_at)
                    self._cache.move_to_end(k)
                    if len(self._cache) > self._cache_limit: self._cache.popitem(last=False)
                self._engine._execute_raw("COMMIT")
                return len(items)
            except Exception as e:
                self._engine._execute_raw("ROLLBACK")
                raise e

    async def save_async(self, str key, value, ttl=None):
        return await asyncio.to_thread(self.save, key, value, ttl)
    
    async def getkey_async(self, str key, deserialize=True):
        return await asyncio.to_thread(self.getkey, key, deserialize)
    
    def get_replication_stream(self, last_id=0):
        return self._engine._bind_and_fetch("SELECT id, key, value, timestamp FROM audit_log WHERE id > ? ORDER BY id ASC", [last_id])

    def sync_from_stream(self, list entries):
        with self._exclusive():
            try:
                self._engine._execute_raw("BEGIN TRANSACTION")
                for e in entries:
                    k, v = e[1], e[2]
                    if v is None: self._engine._bind_and_execute("DELETE FROM kvstore WHERE key=?", [k])
                    else: self._engine._bind_and_execute("INSERT OR REPLACE INTO kvstore (key, value) VALUES (?, ?)", [k, v])
                self._engine._execute_raw("COMMIT")
            except Exception as e:
                self._engine._execute_raw("ROLLBACK")
                raise e

    def import_data(self, str file_path):
        self._ensure_kv("kyi")
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")
        
        with open(file_path, "r") as f:
            if file_path.endswith(".json"):
                data = json.load(f)
                if isinstance(data, dict):
                    self.save_many(list(data.items()))
                elif isinstance(data, list):
                    # Assume list of [key, value] pairs
                    self.save_many(data)
                else:
                    raise ValueError("JSON must be a dictionary or list of pairs.")
            
            elif file_path.endswith(".csv"):
                import csv
                reader = csv.reader(f)
                items = []
                headers = next(reader, None) # Skip header?
                # Heuristic: if header looks like Key,Value then skip, else use
                if headers and headers[0].lower() == "key" and headers[1].lower() == "value":
                    pass 
                else:
                    if headers: items.append((headers[0], headers[1])) 
                
                for row in reader:
                    if len(row) >= 2:
                        items.append((row[0], row[1]))
                self.save_many(items)
            else:
                raise ValueError("Unsupported format. Use .json or .csv")

    def export_data(self, str file_path, str fmt="csv"):
        self._ensure_kv("kye")
        data = {}
        # Use iteration to fetch all active keys
        for k in self:
            data[k] = self.getkey(k)
            
        base_dir = os.path.dirname(file_path) or "."
        tmp_fd = None
        tmp_path = None
        try:
            tmp_fd, tmp_path = tempfile.mkstemp(prefix=".kycli_export_", dir=base_dir)
            if fmt == "json":
                with os.fdopen(tmp_fd, "w") as f:
                    json.dump(data, f, indent=2)
            elif fmt == "csv":
                import csv
                with os.fdopen(tmp_fd, "w", newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow(["Key", "Value"])
                    for k, v in data.items():
                        writer.writerow([k, json.dumps(v) if isinstance(v, (dict, list)) else v])
            else:
                os.close(tmp_fd)
                raise ValueError("Unsupported format. Use 'json' or 'csv'")

            os.replace(tmp_path, file_path)
        except Exception:
            if tmp_fd is not None:
                try:
                    os.close(tmp_fd)
                except Exception:
                    pass
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass
            raise

    def export_audit(self, str file_path, str fmt="json", since=None, until=None):
        rows = self._engine._bind_and_fetch("SELECT key, value, timestamp FROM audit_log ORDER BY id DESC", [])
        result = []
        for row in rows:
            timestamp = row[2]
            if since and timestamp < since:
                continue
            if until and timestamp > until:
                continue
            result.append({"key": row[0], "value": self._decode_storage_value(self._security.decrypt(row[1])) if row[1] is not None else None, "timestamp": timestamp})

        if fmt == "json":
            base_dir = os.path.dirname(file_path) or "."
            fd, tmp_path = tempfile.mkstemp(prefix=".kycli_audit_", dir=base_dir)
            try:
                with os.fdopen(fd, "w") as f:
                    json.dump(result, f, indent=2)
                os.replace(tmp_path, file_path)
            except Exception:
                try:
                    os.close(fd)
                except Exception:
                    pass
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
                raise
        elif fmt == "csv":
            import csv
            base_dir = os.path.dirname(file_path) or "."
            fd, tmp_path = tempfile.mkstemp(prefix=".kycli_audit_", dir=base_dir)
            try:
                with os.fdopen(fd, "w", newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow(["Key", "Value", "Timestamp"])
                    for item in result:
                        writer.writerow([item["key"], item["value"], item["timestamp"]])
                os.replace(tmp_path, file_path)
            except Exception:
                try:
                    os.close(fd)
                except Exception:
                    pass
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
                raise
        else:
            raise ValueError("Unsupported format. Use 'json' or 'csv'")
        return len(result)

    def getkey(self, str key_pattern, deserialize=True):
        self._ensure_kv("kyg")
        k = key_pattern.lower().strip()
        results = self._engine._bind_and_fetch("""
            SELECT value, expires_at, (expires_at < datetime('now')) as is_expired
            FROM kvstore WHERE key = ?
        """, [k])
        
        if results:
            raw_val, exp_at, is_expired = results[0][0], results[0][1], int(results[0][2]) if results[0][2] else 0
            if is_expired:
                warnings.warn(f"Key '{k}' expired at {exp_at} and has been moved to archive.", UserWarning)
                self._engine._execute_raw("BEGIN TRANSACTION")
                self._engine._bind_and_execute("INSERT INTO archive (key, value) VALUES (?, ?)", [k, raw_val])
                self._engine._bind_and_execute("DELETE FROM kvstore WHERE key = ?", [k])
                self._engine._execute_raw("COMMIT")
                return "Key not found"

            if deserialize and k in self._cache:
                cached_val, cached_exp = self._cache[k]
                if cached_exp is None or datetime.strptime(cached_exp, '%Y-%m-%d %H:%M:%S.%f').replace(tzinfo=timezone.utc) > datetime.now(timezone.utc):
                    self._cache.move_to_end(k)
                    return cached_val
                else:
                    del self._cache[k]

            val_str = self._decode_storage_value(self._security.decrypt(raw_val))
            val = val_str
            if deserialize:
                try: val = json.loads(val_str)
                except: pass
            
            self._cache[k] = (val, exp_at)
            self._cache.move_to_end(k)
            if len(self._cache) > self._cache_limit: self._cache.popitem(last=False)
            return val

        # Path Traversal
        for i in range(len(k), 0, -1):
            if k[i-1] in ('.', '['):
                prefix, path = k[:i-1], k[i-1:]
                results = self._engine._bind_and_fetch("SELECT value FROM kvstore WHERE key = ? AND (expires_at IS NULL OR expires_at > datetime('now'))", [prefix])
                if results:
                    val_str = self._decode_storage_value(self._security.decrypt(results[0][0]))
                    try:
                        return self._query.navigate(json.loads(val_str), path)
                    except: continue

        # Regex
        results = self._engine._bind_and_fetch("SELECT key, value FROM kvstore WHERE (expires_at IS NULL OR expires_at > datetime('now'))", [])
        try: regex = re.compile(key_pattern, re.IGNORECASE)
        except: return "Key not found"
        matches = {}
        for row in results:
            if regex.search(row[0]):
                d_val = self._security.decrypt(row[1])
                d_val = self._decode_storage_value(d_val)
                try: matches[row[0]] = json.loads(d_val) if deserialize else d_val
                except: matches[row[0]] = d_val
        return matches if matches else "Key not found"

    def list_keys(self, str pattern=None):
        self._ensure_kv("kyl")
        if pattern:
            results = self._engine._bind_and_fetch("SELECT key FROM kvstore WHERE (expires_at IS NULL OR expires_at > datetime('now'))", [])
            try: regex = re.compile(pattern, re.IGNORECASE)
            except: return []
            return [row[0] for row in results if regex.search(row[0])]
        else:
            results = self._engine._bind_and_fetch("SELECT key FROM kvstore WHERE (expires_at IS NULL OR expires_at > datetime('now'))", [])
            return [row[0] for row in results]

    def listkeys(self, str pattern=None): return self.list_keys(pattern)

    def patch(self, str key_path, value, ttl=None):
        k = key_path.lower().strip()
        with self._exclusive():
            return self._patch_locked(k, value, ttl=ttl)

    def _patch_locked(self, str k, value, ttl=None):
        # Assumes the caller already holds self._exclusive().
        self._ensure_kv("kypatch")
        self._ensure_write_allowed()
        prefix, path = k, ""
        found = False
        for i in range(len(k), 0, -1):
            if k[i-1] in ('.', '['):
                prefix, path = k[:i-1], k[i-1:]
                if prefix in self:
                    found = True
                    break
        if not found and ('.' in k or '[' in k):
            fs = min([k.find(c) for c in ('.', '[') if c in k])
            prefix, path = k[:fs], k[fs:]

        existing = self.getkey(prefix, deserialize=True)
        if existing == "Key not found":
            existing = {} if path.startswith('.') else []
        updated = self._query.patch_value(existing, path, value)
        return self._save_locked(prefix, updated, ttl=ttl)

    def push(self, key, value=_MISSING, unique=False, ttl=None, priority=None):
        with self._exclusive():
            wtype = self._get_type()
            if wtype != "kv":
                self._ensure_write_allowed()
                v = key if value is _MISSING else value
                storage_payload, _ = self._encode_storage_value(v)
                enc_val = self._security.encrypt(storage_payload)
                prio = 0 if priority is None else int(priority)
                available_at = None
                if ttl:
                    available_at = (datetime.now(timezone.utc) + timedelta(seconds=self._parse_ttl(ttl))).strftime('%Y-%m-%d %H:%M:%S.%f')
                with self._queue_lock:
                    try:
                        self._engine._execute_raw("BEGIN IMMEDIATE")
                        self._engine._bind_and_execute(
                            "INSERT INTO queue_items (value, priority, available_at) VALUES (?, ?, ?)",
                            [enc_val, prio, available_at]
                        )
                        self._engine._execute_raw("COMMIT")
                        return "pushed"
                    except Exception as e:
                        try:
                            self._engine._execute_raw("ROLLBACK")
                        except:
                            pass
                        raise e

            if value is _MISSING:
                raise TypeError("push requires a 'key' argument")

            data = self.getkey(key, deserialize=True)
            if data == "Key not found": data = []
            if not isinstance(data, list): raise TypeError("Not a list")
            if unique and value in data: return "nochange"
            data.append(value)
            return self._save_locked(key, data, ttl=ttl)

    def remove(self, str key, value, ttl=None):
        with self._exclusive():
            self._ensure_kv("kyrem")
            self._ensure_write_allowed()
            data = self.getkey(key, deserialize=True)
            if not isinstance(data, list): raise TypeError("Not a list")
            if value in data:
                data.remove(value)
                return self._save_locked(key, data, ttl=ttl)
            return "nochange"

    def delete(self, str key):
        k = key.lower().strip()
        with self._exclusive():
            self._ensure_kv("kyd")
            self._ensure_write_allowed()
            results = self._engine._bind_and_fetch("SELECT value FROM kvstore WHERE key = ?", [k])
            if not results: return "Key not found"
            val = results[0][0]
            try:
                self._engine._execute_raw("BEGIN TRANSACTION")
                self._engine._bind_and_execute("INSERT INTO archive (key, value) VALUES (?, ?)", [k, val])
                self._engine._bind_and_execute("INSERT INTO audit_log (key, value) VALUES (?, NULL)", [k])
                self._engine._bind_and_execute("DELETE FROM kvstore WHERE key=?", [k])
                self._engine._execute_raw("COMMIT")
                if k in self._cache: del self._cache[k]
                return "Deleted"
            except Exception as e:
                self._engine._execute_raw("ROLLBACK")
                raise e

    def search(self, str query, limit=100, deserialize=True, keys_only=False):
        self._ensure_kv("kyg")
        if keys_only:
            sql = "SELECT kvstore.key FROM kvstore JOIN fts_kvstore ON kvstore.rowid = fts_kvstore.rowid WHERE fts_kvstore MATCH ? AND (kvstore.expires_at IS NULL OR kvstore.expires_at > datetime('now')) ORDER BY rank LIMIT ?"
        else:
            sql = "SELECT kvstore.key, kvstore.value FROM kvstore JOIN fts_kvstore ON kvstore.rowid = fts_kvstore.rowid WHERE fts_kvstore MATCH ? AND (kvstore.expires_at IS NULL OR kvstore.expires_at > datetime('now')) ORDER BY rank LIMIT ?"
        results = self._engine._bind_and_fetch(sql, [query, limit])
        if keys_only: return [row[0] for row in results]
        matches = {}
        for row in results:
            d_val = self._security.decrypt(row[1])
            d_val = self._decode_storage_value(d_val)
            if deserialize:
                try:
                    matches[row[0]] = json.loads(d_val)
                except:
                    matches[row[0]] = d_val
            else:
                matches[row[0]] = d_val
        return matches

    @property
    def cache_keys(self): return list(self._cache.keys())

    def get_history(self, str key=None): return self._audit.get_history(key)
    def restore(self, str key, timestamp=None):
        with self._exclusive():
            res = self._audit.restore(key, timestamp)
            if isinstance(res, tuple) and res[0] == "value_ready":
                if res[3]:
                    return self._patch_locked(res[1] + res[3], res[2])
                return self._save_locked(res[1], res[2])
            return res
    def restore_to(self, str ts):
        with self._exclusive():
            res = self._audit.restore_to(ts)
            # restore_to bulk-swaps kvstore directly via raw SQL, bypassing
            # the normal save()/delete() cache-sync path.
            self._cache.clear()
            return res
    def compact(self, int retention_days=15):
        with self._exclusive():
            return self._audit.compact(retention_days)
    def optimize_index(self):
        self._ensure_kv("kyfo")
        self._engine._execute_raw("INSERT INTO fts_kvstore(fts_kvstore) VALUES('optimize')")

    def view_prefix(self, str prefix, limit=100):
        self._ensure_kv("kyl")
        p = f"{prefix.lower()}%"
        rows = self._engine._bind_and_fetch(
            "SELECT key, value FROM kvstore WHERE key LIKE ? AND (expires_at IS NULL OR expires_at > datetime('now')) ORDER BY key LIMIT ?",
            [p, int(limit)]
        )
        result = {}
        for row in rows:
            val = self._security.decrypt(row[1])
            try:
                result[row[0]] = json.loads(val)
            except Exception:
                result[row[0]] = val
        return result

    def get_stats(self):
        stats = {"workspace_type": self._get_type()}
        stats["key_count"] = len(self) if self._get_type() == "kv" else 0
        stats["queue_depth"] = self.count() if self._get_type() != "kv" else 0
        rows = self._engine._bind_and_fetch("SELECT COUNT(*) FROM kvstore WHERE expires_at IS NOT NULL", [])
        stats["ttl_count"] = int(rows[0][0]) if rows else 0
        rows = self._engine._bind_and_fetch("SELECT COUNT(*) FROM archive", [])
        stats["archived_count"] = int(rows[0][0]) if rows else 0
        rows = self._engine._bind_and_fetch("SELECT COUNT(*) FROM audit_log", [])
        stats["audit_count"] = int(rows[0][0]) if rows else 0
        if os.path.exists(self._real_db_path):
            stats["db_size_bytes"] = os.path.getsize(self._real_db_path)
        else:
            stats["db_size_bytes"] = 0
        return stats

    def backup(self, str destination_path):
        with self._exclusive():
            pass  # lock + reload + persist: ensures the on-disk file is fresh and durable before copying
        target = destination_path
        if os.path.exists(target):
            target = target + ".1"
            idx = 1
            while os.path.exists(target):
                idx += 1
                target = f"{destination_path}.{idx}"
        shutil.copy2(self._real_db_path, target)
        return target

    def restore_backup(self, str source_path):
        if not os.path.exists(source_path):
            raise FileNotFoundError(f"File not found: {source_path}")
        lock = _ProcessLock(self._lock_path)
        lock.acquire()
        try:
            shutil.copy2(source_path, self._real_db_path)
            self._reload_locked()
        finally:
            lock.release()
        return self._real_db_path

    def rotate_master_key(self, str new_key, str old_key=None, bint dry_run=False, bint backup=False, int batch=500, bint verify=True):
        if not new_key or not str(new_key).strip():
            raise ValueError("New master key is required")

        if dry_run:
            return self._rotate_master_key_locked(new_key, old_key, dry_run, backup, batch, verify)
        with self._exclusive():
            return self._rotate_master_key_locked(new_key, old_key, dry_run, backup, batch, verify)

    def _rotate_master_key_locked(self, str new_key, str old_key, bint dry_run, bint backup, int batch, bint verify):
        cdef SecurityManager old_sec
        cdef SecurityManager new_sec

        if old_key:
            old_sec = SecurityManager(old_key)
        else:
            old_sec = SecurityManager("")
        new_sec = SecurityManager(new_key)

        cdef list tables = ["kvstore", "audit_log", "archive"]
        cdef int i
        cdef str tbl
        cdef list enc_counts = []
        cdef int total_enc = 0
        cdef list rows

        for i in range(len(tables)):
            tbl = tables[i]
            try:
                rows = self._engine._bind_and_fetch(f"SELECT COUNT(*) FROM {tbl} WHERE value LIKE 'enc:%'", [])
                if rows:
                    enc_counts.append(int(rows[0][0]))
                    total_enc += int(rows[0][0])
                else:
                    enc_counts.append(0)
            except Exception:
                enc_counts.append(0)

        if total_enc > 0 and (old_key is None or not str(old_key).strip()):
            raise ValueError("Old master key is required to rotate encrypted values")

        if backup and not dry_run and os.path.exists(self._real_db_path):
            backup_path = self._real_db_path + ".bak"
            if os.path.exists(backup_path):
                idx = 1
                while True:
                    candidate = f"{backup_path}.{idx}"
                    if not os.path.exists(candidate):
                        backup_path = candidate
                        break
                    idx += 1
            shutil.copy2(self._real_db_path, backup_path)

        cdef int rotated = 0
        cdef int offset
        cdef str val
        cdef str plain
        cdef str new_val

        try:
            if not dry_run:
                self._engine._execute_raw("BEGIN TRANSACTION")

            for i in range(len(tables)):
                tbl = tables[i]
                offset = 0
                while True:
                    rows = self._engine._bind_and_fetch(f"SELECT rowid, value FROM {tbl} LIMIT ? OFFSET ?", [batch, offset])
                    if not rows:
                        break
                    for row in rows:
                        if row[1] is None:
                            continue
                        val = row[1]
                        if not isinstance(val, str):
                            val = str(val)
                        if val.startswith("enc:"):
                            plain = old_sec.decrypt(val)
                            if plain == "[DECRYPTION FAILED: Incorrect master key]" or plain == "[ENCRYPTED: Provide a master key to view this value]":
                                raise ValueError("Old master key is invalid")
                        else:
                            plain = val

                        new_val = new_sec.encrypt(plain)
                        if not dry_run:
                            self._engine._bind_and_execute(f"UPDATE {tbl} SET value = ? WHERE rowid = ?", [new_val, row[0]])
                        rotated += 1
                    offset += batch

            if not dry_run:
                self._engine._execute_raw("COMMIT")
                self._security = new_sec
                self._cache.clear()
        except Exception as e:
            if not dry_run:
                try: self._engine._execute_raw("ROLLBACK")
                except: pass
            raise e

        if verify and not dry_run:
            for i in range(len(tables)):
                tbl = tables[i]
                rows = self._engine._bind_and_fetch(f"SELECT value FROM {tbl} WHERE value LIKE 'enc:%' LIMIT 10", [])
                for row in rows:
                    val = row[0]
                    plain = new_sec.decrypt(val)
                    if plain == "[DECRYPTION FAILED: Incorrect master key]" or plain == "[ENCRYPTED: Provide a master key to view this value]":
                        raise ValueError("Verification failed after rotation")

        return rotated

    def __contains__(self, str key):
        self._ensure_kv("kyg")
        res = self._engine._bind_and_fetch("SELECT 1 FROM kvstore WHERE key = ? AND (expires_at IS NULL OR expires_at > datetime('now'))", [key.lower().strip()])
        return len(res) > 0

    def __iter__(self):
        self._ensure_kv("kyl")
        res = self._engine._bind_and_fetch("SELECT key FROM kvstore WHERE (expires_at IS NULL OR expires_at > datetime('now'))", [])
        for row in res: yield row[0]

    def __len__(self):
        if self._get_type() != "kv":
            res = self._engine._bind_and_fetch("SELECT COUNT(*) FROM queue_items", [])
            return int(res[0][0]) if res else 0
        res = self._engine._bind_and_fetch("SELECT COUNT(*) FROM kvstore WHERE (expires_at IS NULL OR expires_at > datetime('now'))", [])
        return int(res[0][0]) if res else 0

    def __getitem__(self, str k):
        self._ensure_kv("kyg")
        v = self.getkey(k)
        if v == "Key not found": raise KeyError(k)
        return v
    def __setitem__(self, str k, v):
        self._ensure_kv("kys")
        self.save(k, v)
    def __delitem__(self, str k): 
        self._ensure_kv("kyd")
        if self.delete(k) == "Key not found": raise KeyError(k)
