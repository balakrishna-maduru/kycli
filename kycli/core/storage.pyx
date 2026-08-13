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
from kycli.logging_utils import get_logger

cdef object _MISSING = object()
_RBAC_BOOTSTRAP_PRINCIPAL = "__legacy_owner__"
_RBAC_ANONYMOUS_PRINCIPAL = "anonymous"
_RBAC_ROLES = ("owner", "admin", "writer", "reader")
logger = get_logger("kycli.rbac")

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
    cdef int _lock_depth

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
        self._lock_depth = 0

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
            self._lock_depth += 1
            self._reload_locked()
            yield
            self._persist()
            self._last_sync_fingerprint = self._file_fingerprint()
        finally:
            self._lock_depth -= 1
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
            CREATE TABLE IF NOT EXISTS principals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                token_hash TEXT NOT NULL,
                disabled INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (STRFTIME('%Y-%m-%d %H:%M:%f', 'NOW'))
            )
        """)
        self._engine._execute_raw("""
            CREATE TABLE IF NOT EXISTS workspace_roles (
                principal_id INTEGER NOT NULL REFERENCES principals(id),
                role TEXT NOT NULL,
                granted_by INTEGER,
                granted_at TEXT NOT NULL DEFAULT (STRFTIME('%Y-%m-%d %H:%M:%f', 'NOW')),
                PRIMARY KEY (principal_id)
            )
        """)
        self._engine._execute_raw("""
            CREATE TABLE IF NOT EXISTS key_acl (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                principal_id INTEGER NOT NULL REFERENCES principals(id),
                key_pattern TEXT NOT NULL,
                allow_verbs TEXT,
                deny_verbs TEXT,
                priority INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (STRFTIME('%Y-%m-%d %H:%M:%f', 'NOW'))
            )
        """)
        self._engine._execute_raw("CREATE INDEX IF NOT EXISTS idx_principals_name ON principals(name)")
        self._engine._execute_raw("CREATE INDEX IF NOT EXISTS idx_principals_token_hash ON principals(token_hash)")
        self._engine._execute_raw("CREATE INDEX IF NOT EXISTS idx_key_acl_principal ON key_acl(principal_id)")

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

    def _sql_text_literal(self, value):
        if value is None:
            return "NULL"
        text = str(value)
        if "\x00" in text:
            raise ValueError("NUL bytes are not supported in persisted text fields")
        return "'" + text.replace("'", "''") + "'"

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

        # Dump RBAC Principals
        rows = self._engine._bind_and_fetch("SELECT id, name, token_hash, disabled, created_at FROM principals ORDER BY id", [])
        for r in rows:
            p_id, name, token_hash, disabled, created_at = r[0], r[1], r[2], r[3], r[4]
            sql_stmts.append(
                f"INSERT INTO principals (id, name, token_hash, disabled, created_at) VALUES ({p_id}, {self._sql_text_literal(name)}, {self._sql_text_literal(token_hash)}, {int(disabled or 0)}, {self._sql_text_literal(created_at)});"
            )

        # Dump RBAC Workspace Roles
        rows = self._engine._bind_and_fetch("SELECT principal_id, role, granted_by, granted_at FROM workspace_roles ORDER BY principal_id", [])
        for r in rows:
            principal_id, role, granted_by, granted_at = r[0], r[1], r[2], r[3]
            granted_by_val = "NULL" if granted_by is None else str(int(granted_by))
            sql_stmts.append(
                f"INSERT OR REPLACE INTO workspace_roles (principal_id, role, granted_by, granted_at) VALUES ({int(principal_id)}, {self._sql_text_literal(role)}, {granted_by_val}, {self._sql_text_literal(granted_at)});"
            )

        # Dump RBAC Key ACLs
        rows = self._engine._bind_and_fetch("SELECT id, principal_id, key_pattern, allow_verbs, deny_verbs, priority, created_at FROM key_acl ORDER BY id", [])
        for r in rows:
            acl_id, principal_id, pattern, allow_v, deny_v, priority, created_at = r[0], r[1], r[2], r[3], r[4], r[5], r[6]
            allow_val = self._sql_text_literal(allow_v)
            deny_val = self._sql_text_literal(deny_v)
            sql_stmts.append(
                f"INSERT INTO key_acl (id, principal_id, key_pattern, allow_verbs, deny_verbs, priority, created_at) VALUES ({int(acl_id)}, {int(principal_id)}, {self._sql_text_literal(pattern)}, {allow_val}, {deny_val}, {int(priority or 0)}, {self._sql_text_literal(created_at)});"
            )

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

    def set_type(self, str type_name, token=None):
        if not type_name or not str(type_name).strip():
            raise ValueError("Workspace type is required")
        t = str(type_name).strip().lower()
        if t not in ("kv", "queue", "stack", "priority_queue"):
            raise ValueError(f"Invalid workspace type: {type_name}")

        with self._exclusive():
            self._ensure_allowed("manage_workspace", token=token)
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
            return self._set_workspace_setting_locked(key, val)

    def _set_workspace_setting_locked(self, str key, value):
        val = None if value is None else str(value)
        self._engine._bind_and_execute("INSERT OR REPLACE INTO workspace_meta (key, value) VALUES (?, ?)", [key, val])
        return val

    def _rbac_enabled(self):
        return self._get_workspace_setting("rbac_enabled", "0") == "1"

    def _permission_map(self):
        return {
            "owner": {"read", "write", "delete", "manage_acl", "manage_readonly", "manage_workspace", "admin"},
            "admin": {"read", "write", "delete", "manage_acl", "manage_readonly", "manage_workspace"},
            "writer": {"read", "write", "delete"},
            "reader": {"read"},
        }

    def _normalize_csv_verbs(self, verbs):
        if verbs is None:
            return None
        if isinstance(verbs, str):
            items = verbs.split(",")
        else:
            items = list(verbs)
        cleaned = []
        for item in items:
            val = str(item).strip().lower()
            if val:
                cleaned.append(val)
        return ",".join(sorted(set(cleaned))) if cleaned else None

    def _split_csv_verbs(self, raw):
        if not raw:
            return set()
        return {part.strip().lower() for part in str(raw).split(",") if str(part).strip()}

    def _normalize_principal_name(self, name):
        if name is None:
            raise ValueError("Principal name is required")
        normalized = str(name).strip()
        if not normalized:
            raise ValueError("Principal name is required")
        return normalized

    def _audit_event_locked(self, str event_key, payload):
        storage_payload = json.dumps(payload, sort_keys=True, default=str)
        self._engine._bind_and_execute(
            "INSERT INTO audit_log (key, value) VALUES (?, ?)",
            [event_key, self._security.encrypt(storage_payload)],
        )

    def _get_principal_row(self, str name):
        rows = self._engine._bind_and_fetch(
            """
            SELECT p.id, p.name, p.token_hash, p.disabled, wr.role
            FROM principals p
            LEFT JOIN workspace_roles wr ON wr.principal_id = p.id
            WHERE p.name = ?
            """,
            [name],
        )
        if not rows:
            return None
        row = rows[0]
        return {
            "id": int(row[0]),
            "name": row[1],
            "token_hash": row[2],
            "disabled": bool(int(row[3] or 0)),
            "role": row[4],
        }

    def _get_principal_by_token(self, str token):
        if not token:
            return None
        token_hash = self._security.hash_token(token)
        rows = self._engine._bind_and_fetch(
            """
            SELECT p.id, p.name, p.token_hash, p.disabled, wr.role
            FROM principals p
            LEFT JOIN workspace_roles wr ON wr.principal_id = p.id
            WHERE p.token_hash = ?
            """,
            [token_hash],
        )
        if not rows:
            return None
        row = rows[0]
        if int(row[3] or 0) != 0:
            return None
        return {
            "id": int(row[0]),
            "name": row[1],
            "token_hash": row[2],
            "disabled": False,
            "role": row[4],
        }

    def _effective_token(self, token=None, access_key=None):
        if token is not None:
            return token
        if access_key is not None:
            return access_key
        token = os.environ.get("KYCLI_TOKEN")
        if token:
            return token
        return os.environ.get("KYCLI_ACCESS_KEY")

    def _resolve_principal(self, token=None, access_key=None):
        effective_token = self._effective_token(token, access_key=access_key)
        principal = self._get_principal_by_token(effective_token) if effective_token else None
        if principal is not None:
            principal["auth_source"] = "token"
            return principal
        anon = self._get_principal_row(_RBAC_ANONYMOUS_PRINCIPAL)
        if anon and not anon["disabled"]:
            anon["auth_source"] = "anonymous"
            return anon
        return None

    def _principal_has_permission(self, principal, str verb, key=None):
        if principal is None:
            return False
        allowed = self._permission_map().get(principal.get("role") or "", set())
        if key is not None:
            rows = self._engine._bind_and_fetch(
                """
                SELECT ka.allow_verbs, ka.deny_verbs, ka.key_pattern
                FROM key_acl ka
                WHERE ka.principal_id = ?
                ORDER BY ka.priority DESC, ka.id ASC
                """,
                [principal["id"]],
            )
            key_text = str(key)
            for row in rows:
                try:
                    if not re.search(row[2], key_text, re.IGNORECASE):
                        continue
                except Exception:
                    continue
                deny_verbs = self._split_csv_verbs(row[1])
                allow_verbs = self._split_csv_verbs(row[0])
                if verb in deny_verbs:
                    return False
                if verb in allow_verbs:
                    return True
        return verb in allowed

    def _log_permission_denied_locked(self, str verb, key=None, principal=None):
        self._audit_event_locked(
            "_rbac.denied",
            {
                "principal": principal["name"] if principal else None,
                "verb": verb,
                "key": key,
            },
        )

    def _log_permission_denied(self, str verb, key=None, principal=None):
        logger.warning(
            "rbac_denied principal=%s verb=%s key=%s",
            principal["name"] if principal else None,
            verb,
            key,
        )
        if self._lock_depth > 0:
            self._log_permission_denied_locked(verb, key=key, principal=principal)
            return
        with self._exclusive():
            self._log_permission_denied_locked(verb, key=key, principal=principal)

    def _ensure_allowed(self, str verb, key=None, access_key=None, token=None):
        readonly = self._get_workspace_setting("readonly", "0")
        if verb not in ("read", "manage_readonly") and readonly == "1":
            raise PermissionError("Workspace is read-only")
        if not self._rbac_enabled():
            if verb == "read":
                return
            required_key = self._get_workspace_setting("access_key", None)
            effective_key = access_key if access_key is not None else os.environ.get("KYCLI_ACCESS_KEY")
            if required_key and required_key != effective_key:
                raise PermissionError("Workspace access key required")
            return
        principal = self._resolve_principal(token, access_key=access_key)
        if not self._principal_has_permission(principal, verb, key=key):
            self._log_permission_denied(verb, key=key, principal=principal)
            raise PermissionError("permission denied")

    def _require_principal_row(self, str name):
        principal = self._get_principal_row(name)
        if principal is None:
            raise ValueError(f"Unknown principal: {name}")
        return principal

    def _grant_key_acl_locked(self, str name, str key_pattern, allow=None, deny=None, priority=0):
        principal = self._require_principal_row(name)
        if not key_pattern or not str(key_pattern).strip():
            raise ValueError("Key pattern is required")
        allow_verbs = self._normalize_csv_verbs(allow)
        deny_verbs = self._normalize_csv_verbs(deny)
        if allow_verbs is None and deny_verbs is None:
            raise ValueError("At least one allow/deny verb is required")
        self._engine._bind_and_execute(
            """
            INSERT INTO key_acl (principal_id, key_pattern, allow_verbs, deny_verbs, priority)
            VALUES (?, ?, ?, ?, ?)
            """,
            [principal["id"], str(key_pattern), allow_verbs, deny_verbs, int(priority)],
        )
        self._audit_event_locked(
            "_rbac.grant_key_acl",
            {
                "principal": name,
                "key_pattern": key_pattern,
                "allow": allow_verbs,
                "deny": deny_verbs,
                "priority": int(priority),
            },
        )

    def enable_rbac(self, token=None, access_key=None):
        with self._exclusive():
            self._ensure_allowed("manage_acl", token=token, access_key=access_key)
            if self._rbac_enabled():
                return self.get_rbac_status()
            principal_count = self._engine._bind_and_fetch("SELECT COUNT(*) FROM principals", [])
            principal_total = int(principal_count[0][0]) if principal_count else 0
            stored_access_key = self._get_workspace_setting("access_key", None)
            if stored_access_key:
                existing = self._get_principal_row(_RBAC_BOOTSTRAP_PRINCIPAL)
                token_hash = self._security.hash_token(stored_access_key)
                if existing is None:
                    self._engine._bind_and_execute(
                        "INSERT INTO principals (name, token_hash, disabled) VALUES (?, ?, 0)",
                        [_RBAC_BOOTSTRAP_PRINCIPAL, token_hash],
                    )
                else:
                    self._engine._bind_and_execute(
                        "UPDATE principals SET token_hash = ?, disabled = 0 WHERE id = ?",
                        [token_hash, existing["id"]],
                    )
                bootstrap = self._require_principal_row(_RBAC_BOOTSTRAP_PRINCIPAL)
                self._engine._bind_and_execute(
                    "INSERT OR REPLACE INTO workspace_roles (principal_id, role, granted_at) VALUES (?, ?, STRFTIME('%Y-%m-%d %H:%M:%f', 'NOW'))",
                    [bootstrap["id"], "owner"],
                )
            else:
                owner_count = self._engine._bind_and_fetch("SELECT COUNT(*) FROM workspace_roles WHERE role = 'owner'", [])
                if principal_total == 0 or int(owner_count[0][0]) == 0:
                    raise ValueError("Create an owner principal first with 'kyacl user add <name> --role owner'")
            self._set_workspace_setting_locked("rbac_enabled", "1")
            self._audit_event_locked("_rbac.enable", {"enabled": True})
            return self.get_rbac_status()

    def disable_rbac(self, token=None, access_key=None):
        with self._exclusive():
            self._ensure_allowed("manage_acl", token=token, access_key=access_key)
            self._set_workspace_setting_locked("rbac_enabled", "0")
            self._audit_event_locked("_rbac.disable", {"enabled": False})
            return self.get_rbac_status()

    def get_rbac_status(self, token=None):
        principal_count = self._engine._bind_and_fetch("SELECT COUNT(*) FROM principals WHERE disabled = 0", [])
        current = self._resolve_principal(token) if self._rbac_enabled() else None
        return {
            "rbac_enabled": self._rbac_enabled(),
            "principal_count": int(principal_count[0][0]) if principal_count else 0,
            "current_principal": current["name"] if current else None,
            "current_role": current.get("role") if current else None,
        }

    def create_principal(self, name, role=None, token=None, access_key=None):
        principal_name = self._normalize_principal_name(name)
        role_name = None if role is None else str(role).strip().lower()
        if role_name is not None and role_name not in _RBAC_ROLES:
            raise ValueError(f"Invalid role: {role}")
        auth_token = token
        new_token = self._security.generate_token()
        with self._exclusive():
            self._ensure_allowed("manage_acl", token=auth_token, access_key=access_key)
            existing = self._get_principal_row(principal_name)
            if existing is not None:
                raise ValueError(f"Principal already exists: {principal_name}")
            self._engine._bind_and_execute(
                "INSERT INTO principals (name, token_hash, disabled) VALUES (?, ?, 0)",
                [principal_name, self._security.hash_token(new_token)],
            )
            created = self._require_principal_row(principal_name)
            if role_name is not None:
                self._engine._bind_and_execute(
                    "INSERT OR REPLACE INTO workspace_roles (principal_id, role, granted_at) VALUES (?, ?, STRFTIME('%Y-%m-%d %H:%M:%f', 'NOW'))",
                    [created["id"], role_name],
                )
            self._audit_event_locked("_rbac.user_add", {"principal": principal_name, "role": role_name})
        return new_token

    def list_principals(self, token=None):
        self._ensure_allowed("manage_acl", token=token)
        rows = self._engine._bind_and_fetch(
            """
            SELECT p.name, p.disabled, wr.role
            FROM principals p
            LEFT JOIN workspace_roles wr ON wr.principal_id = p.id
            ORDER BY p.name
            """,
            [],
        )
        return [
            {
                "name": row[0],
                "disabled": bool(int(row[1] or 0)),
                "role": row[2],
            }
            for row in rows
        ]

    def disable_principal(self, name, token=None, access_key=None):
        principal_name = self._normalize_principal_name(name)
        with self._exclusive():
            self._ensure_allowed("manage_acl", token=token, access_key=access_key)
            principal = self._require_principal_row(principal_name)
            self._engine._bind_and_execute("UPDATE principals SET disabled = 1 WHERE id = ?", [principal["id"]])
            self._audit_event_locked("_rbac.user_disable", {"principal": principal_name})
        return principal_name

    def rotate_principal_token(self, name, token=None, access_key=None):
        principal_name = self._normalize_principal_name(name)
        auth_token = token
        new_token = self._security.generate_token()
        with self._exclusive():
            self._ensure_allowed("manage_acl", token=auth_token, access_key=access_key)
            principal = self._require_principal_row(principal_name)
            self._engine._bind_and_execute(
                "UPDATE principals SET token_hash = ?, disabled = 0 WHERE id = ?",
                [self._security.hash_token(new_token), principal["id"]],
            )
            self._audit_event_locked("_rbac.rotate_token", {"principal": principal_name})
        return new_token

    def grant_role(self, name, role, key_pattern=None, allow=None, deny=None, priority=0, token=None, access_key=None):
        principal_name = self._normalize_principal_name(name)
        role_name = str(role).strip().lower()
        if role_name not in _RBAC_ROLES:
            raise ValueError(f"Invalid role: {role}")
        with self._exclusive():
            self._ensure_allowed("manage_acl", token=token, access_key=access_key)
            principal = self._require_principal_row(principal_name)
            self._engine._bind_and_execute(
                "INSERT OR REPLACE INTO workspace_roles (principal_id, role, granted_at) VALUES (?, ?, STRFTIME('%Y-%m-%d %H:%M:%f', 'NOW'))",
                [principal["id"], role_name],
            )
            if key_pattern is not None or allow is not None or deny is not None:
                self._grant_key_acl_locked(principal_name, key_pattern, allow=allow, deny=deny, priority=priority)
            self._audit_event_locked("_rbac.role_grant", {"principal": principal_name, "role": role_name})
        return role_name

    def grant_key_acl(self, name, key_pattern, allow=None, deny=None, priority=0, token=None, access_key=None):
        principal_name = self._normalize_principal_name(name)
        with self._exclusive():
            self._ensure_allowed("manage_acl", token=token, access_key=access_key)
            self._grant_key_acl_locked(principal_name, key_pattern, allow=allow, deny=deny, priority=priority)
        return principal_name

    def revoke_role(self, name, token=None, access_key=None):
        principal_name = self._normalize_principal_name(name)
        with self._exclusive():
            self._ensure_allowed("manage_acl", token=token, access_key=access_key)
            principal = self._require_principal_row(principal_name)
            self._engine._bind_and_execute("DELETE FROM workspace_roles WHERE principal_id = ?", [principal["id"]])
            self._engine._bind_and_execute("DELETE FROM key_acl WHERE principal_id = ?", [principal["id"]])
            self._audit_event_locked("_rbac.role_revoke", {"principal": principal_name})
        return principal_name

    def list_roles(self, name=None, token=None):
        self._ensure_allowed("manage_acl", token=token)
        rows = self._engine._bind_and_fetch(
            """
            SELECT p.name, wr.role, p.disabled,
                   (SELECT COUNT(*) FROM key_acl ka WHERE ka.principal_id = p.id)
            FROM principals p
            LEFT JOIN workspace_roles wr ON wr.principal_id = p.id
            WHERE (? IS NULL OR p.name = ?)
            ORDER BY p.name
            """,
            [name, name],
        )
        result = []
        for row in rows:
            result.append({
                "name": row[0],
                "role": row[1],
                "disabled": bool(int(row[2] or 0)),
                "key_acl_count": int(row[3] or 0),
            })
        return result

    def whoami(self, token=None):
        principal = self._resolve_principal(token) if self._rbac_enabled() else None
        return {
            "rbac_enabled": self._rbac_enabled(),
            "principal": principal["name"] if principal else None,
            "role": principal.get("role") if principal else None,
            "auth_source": principal.get("auth_source") if principal else None,
        }

    def check_permission(self, token, str verb, key=None):
        try:
            self._ensure_allowed(verb, key=key, token=token)
            return True
        except PermissionError:
            return False

    def set_default_ttl(self, ttl, token=None):
        with self._exclusive():
            self._ensure_allowed("manage_workspace", token=token)
            parsed = self._parse_ttl(ttl) if ttl is not None else None
            self._set_workspace_setting_locked("default_ttl", parsed)
            return parsed

    def get_default_ttl(self):
        value = self._get_workspace_setting("default_ttl", None)
        return int(value) if value not in (None, "") else None

    def set_read_only(self, enabled, token=None):
        with self._exclusive():
            self._ensure_allowed("manage_readonly", token=token)
            self._set_workspace_setting_locked("readonly", "1" if enabled else "0")
            self._audit_event_locked("_rbac.readonly", {"enabled": bool(enabled)})
            return enabled

    def get_read_only(self):
        return self._get_workspace_setting("readonly", "0") == "1"

    def set_access_key(self, str access_key=None, token=None):
        with self._exclusive():
            self._ensure_allowed("manage_acl", token=token)
            self._set_workspace_setting_locked("access_key", access_key)
            self._audit_event_locked("_rbac.access_key", {"configured": access_key is not None})
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

    def peek(self, bint deserialize=True, token=None):
        self._ensure_queue("peek")
        self._ensure_allowed("read", token=token)
        order_by = self._queue_order()
        if order_by is None:
            raise TypeError("'peek' not supported")
        with self._queue_lock:
            rows = self._engine._bind_and_fetch(f"SELECT value FROM queue_items WHERE {self._queue_where_clause()} ORDER BY {order_by} LIMIT 1", [])
        if not rows:
            return None
        return self._queue_deserialize(rows[0][0], deserialize)

    def pop(self, bint deserialize=True, count=1, lease=None, token=None):
        batch_size = int(count) if count else 1
        if batch_size < 1:
            raise ValueError("count must be >= 1")
        lease_seconds = self._parse_ttl(lease) if lease else None
        results = []
        with self._exclusive():
            self._ensure_queue("pop")
            self._ensure_allowed("delete", token=token)
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

    def ack(self, str receipt_id, token=None):
        with self._exclusive():
            self._ensure_queue("ack")
            self._ensure_allowed("delete", token=token)
            with self._queue_lock:
                self._engine._execute_raw("BEGIN IMMEDIATE")
                rows = self._engine._bind_and_fetch("SELECT id FROM queue_items WHERE receipt_id = ?", [receipt_id])
                if not rows:
                    self._engine._execute_raw("COMMIT")
                    return "Receipt not found"
                self._engine._bind_and_execute("DELETE FROM queue_items WHERE receipt_id = ?", [receipt_id])
                self._engine._execute_raw("COMMIT")
                return "acked"

    def nack(self, str receipt_id, delay=None, token=None):
        delay_seconds = self._parse_ttl(delay) if delay else None
        available_at = None
        if delay_seconds:
            available_at = (datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)).strftime('%Y-%m-%d %H:%M:%S.%f')
        with self._exclusive():
            self._ensure_queue("nack")
            self._ensure_allowed("write", token=token)
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

    def count(self, token=None):
        self._ensure_queue("count")
        self._ensure_allowed("read", token=token)
        with self._queue_lock:
            res = self._engine._bind_and_fetch("SELECT COUNT(*) FROM queue_items", [])
            return int(res[0][0]) if res else 0

    def clear(self, token=None):
        with self._exclusive():
            self._ensure_queue("clear")
            self._ensure_allowed("delete", token=token)
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

    def save(self, str key, value, ttl=None, token=None):
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
            return self._save_locked(k, value, ttl, token=token)

    def _save_locked(self, str k, value, ttl=None, token=None):
        # Assumes the caller already holds self._exclusive() and has reloaded
        # the freshest on-disk state into self._engine.
        self._ensure_kv("kys")
        self._ensure_allowed("write", key=k, token=token)
        if ttl is None:
            ttl = self.get_default_ttl()

        storage_payload, string_val = self._encode_storage_value(value)
        storage_val = self._security.encrypt(string_val)
        if storage_payload != string_val:
            storage_val = self._security.encrypt(storage_payload)
        expires_at = None
        if ttl:
            expires_at = (datetime.now(timezone.utc) + timedelta(seconds=self._parse_ttl(ttl))).strftime('%Y-%m-%d %H:%M:%S.%f')

        existing = self.getkey(k, deserialize=False, token=token)
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

    def save_many(self, list items, ttl=None, token=None):
        if not items: return 0
        with self._exclusive():
            self._ensure_kv("kys")
            self._ensure_allowed("write", token=token)
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

    def import_data(self, str file_path, token=None):
        self._ensure_kv("kyi")
        self._ensure_allowed("write", token=token)
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")
        
        with open(file_path, "r") as f:
            if file_path.endswith(".json"):
                data = json.load(f)
                if isinstance(data, dict):
                    self.save_many(list(data.items()), token=token)
                elif isinstance(data, list):
                    # Assume list of [key, value] pairs
                    self.save_many(data, token=token)
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
                self.save_many(items, token=token)
            else:
                raise ValueError("Unsupported format. Use .json or .csv")

    def export_data(self, str file_path, str fmt="csv", token=None):
        self._ensure_kv("kye")
        self._ensure_allowed("read", token=token)
        data = {}
        # Use iteration to fetch all active keys
        for k in self.iter_keys(token=token):
            data[k] = self.getkey(k, token=token)
            
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

    def export_audit(self, str file_path, str fmt="json", since=None, until=None, token=None):
        self._ensure_allowed("read", token=token)
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

    def getkey(self, str key_pattern, deserialize=True, token=None):
        self._ensure_kv("kyg")
        self._ensure_allowed("read", key=key_pattern, token=token)
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

    def list_keys(self, str pattern=None, token=None):
        self._ensure_kv("kyl")
        self._ensure_allowed("read", key=pattern, token=token)
        if pattern:
            results = self._engine._bind_and_fetch("SELECT key FROM kvstore WHERE (expires_at IS NULL OR expires_at > datetime('now'))", [])
            try: regex = re.compile(pattern, re.IGNORECASE)
            except: return []
            return [row[0] for row in results if regex.search(row[0])]
        else:
            results = self._engine._bind_and_fetch("SELECT key FROM kvstore WHERE (expires_at IS NULL OR expires_at > datetime('now'))", [])
            return [row[0] for row in results]

    def listkeys(self, str pattern=None, token=None): return self.list_keys(pattern, token=token)

    def patch(self, str key_path, value, ttl=None, token=None):
        k = key_path.lower().strip()
        with self._exclusive():
            return self._patch_locked(k, value, ttl=ttl, token=token)

    def _patch_locked(self, str k, value, ttl=None, token=None):
        # Assumes the caller already holds self._exclusive().
        self._ensure_kv("kypatch")
        self._ensure_allowed("write", key=k, token=token)
        prefix, path = k, ""
        found = False
        for i in range(len(k), 0, -1):
            if k[i-1] in ('.', '['):
                prefix, path = k[:i-1], k[i-1:]
                if self.contains(prefix, token=token):
                    found = True
                    break
        if not found and ('.' in k or '[' in k):
            fs = min([k.find(c) for c in ('.', '[') if c in k])
            prefix, path = k[:fs], k[fs:]

        existing = self.getkey(prefix, deserialize=True, token=token)
        if existing == "Key not found":
            existing = {} if path.startswith('.') else []
        updated = self._query.patch_value(existing, path, value)
        return self._save_locked(prefix, updated, ttl=ttl, token=token)

    def push(self, key, value=_MISSING, unique=False, ttl=None, priority=None, token=None):
        with self._exclusive():
            wtype = self._get_type()
            if wtype != "kv":
                self._ensure_allowed("write", token=token)
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

            data = self.getkey(key, deserialize=True, token=token)
            if data == "Key not found": data = []
            if not isinstance(data, list): raise TypeError("Not a list")
            if unique and value in data: return "nochange"
            data.append(value)
            return self._save_locked(key, data, ttl=ttl, token=token)

    def remove(self, str key, value, ttl=None, token=None):
        with self._exclusive():
            self._ensure_kv("kyrem")
            self._ensure_allowed("write", key=key, token=token)
            data = self.getkey(key, deserialize=True, token=token)
            if not isinstance(data, list): raise TypeError("Not a list")
            if value in data:
                data.remove(value)
                return self._save_locked(key, data, ttl=ttl, token=token)
            return "nochange"

    def delete(self, str key, token=None):
        k = key.lower().strip()
        with self._exclusive():
            self._ensure_kv("kyd")
            self._ensure_allowed("delete", key=k, token=token)
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

    def search(self, str query, limit=100, deserialize=True, keys_only=False, token=None):
        self._ensure_kv("kyg")
        self._ensure_allowed("read", key=query, token=token)
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

    def get_history(self, str key=None, token=None):
        self._ensure_allowed("read", key=key, token=token)
        return self._audit.get_history(key)
    def restore(self, str key, timestamp=None, token=None):
        with self._exclusive():
            self._ensure_allowed("admin", key=key, token=token)
            res = self._audit.restore(key, timestamp)
            if isinstance(res, tuple) and res[0] == "value_ready":
                if res[3]:
                    return self._patch_locked(res[1] + res[3], res[2], token=token)
                return self._save_locked(res[1], res[2], token=token)
            return res
    def restore_to(self, str ts, token=None):
        with self._exclusive():
            self._ensure_allowed("admin", token=token)
            res = self._audit.restore_to(ts)
            # restore_to bulk-swaps kvstore directly via raw SQL, bypassing
            # the normal save()/delete() cache-sync path.
            self._cache.clear()
            return res
    def compact(self, int retention_days=15, token=None):
        with self._exclusive():
            self._ensure_allowed("manage_workspace", token=token)
            return self._audit.compact(retention_days)
    def optimize_index(self):
        self._ensure_kv("kyfo")
        self._engine._execute_raw("INSERT INTO fts_kvstore(fts_kvstore) VALUES('optimize')")

    def view_prefix(self, str prefix, limit=100, token=None):
        self._ensure_kv("kyl")
        self._ensure_allowed("read", key=prefix, token=token)
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

    def get_stats(self, token=None):
        self._ensure_allowed("read", token=token)
        stats = {"workspace_type": self._get_type()}
        stats["key_count"] = len(self) if self._get_type() == "kv" else 0
        stats["queue_depth"] = self.count(token=token) if self._get_type() != "kv" else 0
        rows = self._engine._bind_and_fetch("SELECT COUNT(*) FROM kvstore WHERE expires_at IS NOT NULL", [])
        stats["ttl_count"] = int(rows[0][0]) if rows else 0
        rows = self._engine._bind_and_fetch("SELECT COUNT(*) FROM archive", [])
        stats["archived_count"] = int(rows[0][0]) if rows else 0
        rows = self._engine._bind_and_fetch("SELECT COUNT(*) FROM audit_log", [])
        stats["audit_count"] = int(rows[0][0]) if rows else 0
        stats["rbac_enabled"] = self._rbac_enabled()
        principal_rows = self._engine._bind_and_fetch("SELECT COUNT(*) FROM principals WHERE disabled = 0", [])
        stats["rbac_principal_count"] = int(principal_rows[0][0]) if principal_rows else 0
        if os.path.exists(self._real_db_path):
            stats["db_size_bytes"] = os.path.getsize(self._real_db_path)
        else:
            stats["db_size_bytes"] = 0
        return stats

    def backup(self, str destination_path, token=None):
        with self._exclusive():
            self._ensure_allowed("admin", token=token)
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

    def restore_backup(self, str source_path, token=None):
        if not os.path.exists(source_path):
            raise FileNotFoundError(f"File not found: {source_path}")
        lock = _ProcessLock(self._lock_path)
        lock.acquire()
        try:
            self._ensure_allowed("admin", token=token)
            shutil.copy2(source_path, self._real_db_path)
            self._reload_locked()
        finally:
            lock.release()
        return self._real_db_path

    def rotate_master_key(self, str new_key, str old_key=None, bint dry_run=False, bint backup=False, int batch=500, bint verify=True, token=None, access_key=None):
        if not new_key or not str(new_key).strip():
            raise ValueError("New master key is required")

        if dry_run:
            self._ensure_allowed("admin", token=token, access_key=access_key)
            return self._rotate_master_key_locked(new_key, old_key, dry_run, backup, batch, verify)
        with self._exclusive():
            self._ensure_allowed("admin", token=token, access_key=access_key)
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

    def contains(self, str key, token=None):
        self._ensure_kv("kyg")
        self._ensure_allowed("read", key=key, token=token)
        res = self._engine._bind_and_fetch("SELECT 1 FROM kvstore WHERE key = ? AND (expires_at IS NULL OR expires_at > datetime('now'))", [key.lower().strip()])
        return len(res) > 0

    def iter_keys(self, token=None):
        self._ensure_kv("kyl")
        self._ensure_allowed("read", token=token)
        res = self._engine._bind_and_fetch("SELECT key FROM kvstore WHERE (expires_at IS NULL OR expires_at > datetime('now'))", [])
        for row in res:
            yield row[0]

    def __contains__(self, str key):
        return self.contains(key)

    def __iter__(self):
        return self.iter_keys()

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
