# cython: language_level=3
from .sqlite_defs cimport *
from .engine cimport DatabaseEngine
from .security cimport SecurityManager
from .query cimport QueryEngine
from .audit cimport AuditManager

import os
import json
import re
import warnings
import asyncio
import shutil
from datetime import datetime, timedelta, timezone
import zlib
import struct
from collections import OrderedDict

try:
    from pydantic import BaseModel, ValidationError
except ImportError:
    BaseModel = None
    ValidationError = None

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

    def __init__(self, db_path=None, schema=None, master_key=None, cache_size=1000):
        if db_path is None:
            db_path = os.path.expanduser("~/kydata.db")
        
        dir_name = os.path.dirname(db_path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)

        if master_key is None:
            master_key = os.environ.get("KYCLI_MASTER_KEY")

        self._real_db_path = db_path
        self._engine = DatabaseEngine(":memory:")
        self._security = SecurityManager(master_key)
        self._query = QueryEngine()
        self._audit = AuditManager(self._engine, self._security, self._query)
        
        self._cache = OrderedDict()
        self._cache_limit = cache_size
        self._schema = schema
        self._dirty_keys = set()
        
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
        
        # Queue/Stack Table
        self._engine._execute_raw("""
            CREATE TABLE IF NOT EXISTS queue_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                value TEXT,
                priority INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT (STRFTIME('%Y-%m-%d %H:%M:%f', 'NOW'))
            )
        """)
        
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
        
        if os.path.exists(self._real_db_path) and os.path.getsize(self._real_db_path) > 0:
            try:
                self._load()
            except:
                pass

        # Auto-cleanup: Delete archived items older than 15 days
        self._engine._execute_raw("DELETE FROM archive WHERE (julianday('now') - julianday(deleted_at)) > 15")

        # Load existing data if available
        if os.path.exists(self._real_db_path):
            self._load()

        # TTL Cleanup: Move expired keys to archive before deleting
        self._engine._execute_raw("""
            INSERT INTO archive (key, value)
            SELECT key, value FROM kvstore 
            WHERE expires_at IS NOT NULL AND expires_at < datetime('now')
        """)
        self._engine._execute_raw("DELETE FROM kvstore WHERE expires_at IS NOT NULL AND expires_at < datetime('now')")

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

    def _encrypt(self, str val): return self._security.encrypt(val)
    def _decrypt(self, str val): return self._security.decrypt(val)

    def get_type(self):
        # We need a way to get this without causing getkey recursion
        rows = self._engine._bind_and_fetch("SELECT value FROM kvstore WHERE key = '_sys_type'", [])
        if not rows: return "kv"
        val_str = self._security.decrypt(rows[0][0])
        try: return json.loads(val_str)
        except: return val_str

    def set_type(self, str wtype):
        valid = ["kv", "queue", "stack", "priority_queue"]
        if wtype not in valid: raise ValueError(f"Invalid type: {wtype}")
        current = self.get_type()
        if current == wtype: return
        
        if current != "kv":
            raise ValueError(f"Cannot change type of a {current} workspace")
            
        if self.count() > 0:
            raise ValueError("Cannot change type of non-empty workspace")
        
        # Save directly to bypass set_type check in save()
        storage_val = self._security.encrypt(json.dumps(wtype))
        self._engine._execute_raw("BEGIN TRANSACTION")
        self._engine._bind_and_execute("INSERT OR REPLACE INTO kvstore (key, value) VALUES (?, ?)", ["_sys_type", storage_val])
        self._engine._execute_raw("COMMIT")
        # _persist is called inside __exit__ or manually if needed, 
        # but here we definitely want it on disk.
        self._persist()

    def _persist(self):
        # Dump DB to SQL
        cdef list sql_stmts = ["BEGIN TRANSACTION;", "DELETE FROM kvstore;", "DELETE FROM audit_log;", "DELETE FROM archive;", "DELETE FROM queue_items;"]
        
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
            
        # Dump Queue Items
        rows = self._engine._bind_and_fetch("SELECT value, priority, created_at FROM queue_items", [])
        for r in rows:
            v, p, ca = r[0], r[1], r[2]
            sql_stmts.append(f"INSERT INTO queue_items (value, priority, created_at) VALUES ('{v.replace('\'', '\'\'')}', {p}, '{ca}');")
            
        sql_stmts.append("COMMIT;")
        full_sql = "\n".join(sql_stmts)
        
        # Compress & Encrypt
        compressed = zlib.compress(full_sql.encode('utf-8'))
        encrypted = self._security.encrypt_blob(compressed)
        
        # Write File: Header + EncryptedBlob
        header = b'KYCLI\x01'
        with open(self._real_db_path, "wb") as f:
            f.write(header + encrypted)

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

    def save(self, str key, value, ttl=None):
        if not key or not key.strip(): raise ValueError("Empty key")
        k = key.lower().strip()
        
        if k != "_sys_type":
            wtype = self.get_type()
            if wtype != "kv":
                raise TypeError(f"Operation 'kys' not supported on {wtype} workspace")

        
        if self._schema:
            try:
                if isinstance(value, dict):
                    value = self._schema(**value).model_dump()
                elif isinstance(value, str):
                    value = self._schema.model_validate_json(value).model_dump()
            except ValidationError as e:
                raise ValueError(f"Schema Error: {e}")

        if isinstance(value, (dict, list, bool, int, float)):
            string_val = json.dumps(value)
        else:
            string_val = str(value)

        storage_val = self._security.encrypt(string_val)
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
            self._persist() # Persist to disk
            return status
        except Exception as e:
            try:
                self._engine._execute_raw("ROLLBACK")
            except:
                pass
            raise RuntimeError(f"Save operation failed: {e}")

    def save_many(self, list items, ttl=None):
        if not items: return 0
        exp_at = None
        if ttl:
            exp_at = (datetime.now(timezone.utc) + timedelta(seconds=self._parse_ttl(ttl))).strftime('%Y-%m-%d %H:%M:%S.%f')
        try:
            self._engine._execute_raw("BEGIN TRANSACTION")
            for key, val in items:
                k = key.lower().strip()
                if self._schema and isinstance(val, dict): val = self._schema(**val).model_dump()
                s_val = json.dumps(val) if isinstance(val, (dict, list, bool, int, float)) else str(val)
                st_val = self._security.encrypt(s_val)
                self._engine._bind_and_execute("INSERT OR REPLACE INTO kvstore (key, value, expires_at) VALUES (?, ?, ?)", [k, st_val, exp_at])
                self._engine._bind_and_execute("INSERT INTO audit_log (key, value) VALUES (?, ?)", [k, st_val])
                self._cache[k] = (val, exp_at)
                self._cache.move_to_end(k)
                if len(self._cache) > self._cache_limit: self._cache.popitem(last=False)
            self._engine._execute_raw("COMMIT")
            self._persist()
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
        try:
            self._engine._execute_raw("BEGIN TRANSACTION")
            for e in entries:
                k, v = e[1], e[2]
                if v is None: self._engine._bind_and_execute("DELETE FROM kvstore WHERE key=?", [k])
                else: self._engine._bind_and_execute("INSERT OR REPLACE INTO kvstore (key, value) VALUES (?, ?)", [k, v])
            self._engine._execute_raw("COMMIT")
            self._persist()
        except Exception as e:
            self._engine._execute_raw("ROLLBACK")
            raise e

    def import_data(self, str file_path):
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
        data = {}
        # Use iteration to fetch all active keys
        for k in self:
            data[k] = self.getkey(k)
            
        if fmt == "json":
            with open(file_path, "w") as f:
                json.dump(data, f, indent=2)
        elif fmt == "csv":
            import csv
            with open(file_path, "w", newline='') as f:
                writer = csv.writer(f)
                writer.writerow(["Key", "Value"])
                for k, v in data.items():
                    writer.writerow([k, json.dumps(v) if isinstance(v, (dict, list)) else v])
        else:
            raise ValueError("Unsupported format. Use 'json' or 'csv'")

    def getkey(self, str key_pattern, deserialize=True):
        k = key_pattern.lower().strip()
        
        if k != "_sys_type":
            wtype = self.get_type()
            if wtype != "kv":
                raise TypeError(f"Operation 'kyg' not supported on {wtype} workspace")

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

            val_str = self._security.decrypt(raw_val)
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
                    val_str = self._security.decrypt(results[0][0])
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
                try: matches[row[0]] = json.loads(d_val) if deserialize else d_val
                except: matches[row[0]] = d_val
        return matches if matches else "Key not found"

    def list_keys(self, str pattern=None):
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
        return self.save(prefix, updated, ttl=ttl)

    def push(self, *args, **kwargs):
        # Polymorphic: push(val) for queues, push(key, val) for list-kv
        wtype = self.get_type()
        unique = kwargs.get('unique', False)
        priority = kwargs.get('priority', 0)
        ttl = kwargs.get('ttl')
        
        if len(args) == 2 or (len(args) == 1 and kwargs.get('key')):
            # KV behavior
            key = kwargs.get('key') or args[0]
            val = args[1] if len(args) == 2 else args[0]
            
            data = self.getkey(key, deserialize=True)
            if data == "Key not found": data = []
            if not isinstance(data, list): raise TypeError("Not a list")
            if unique and val in data: return "nochange"
            data.append(val)
            return self.save(key, data, ttl=ttl)
        else:
            # Queue behavior
            if wtype == "kv":
                # Check if it was supposed to be KV but missing key?
                # Usually kypush requires key in KV.
                raise TypeError("Queue 'push' requires a 'key' argument in KV workspace")
            
            val = args[0]
            s_val = json.dumps(val) if isinstance(val, (dict, list, bool, int, float)) else str(val)
            st_val = self._security.encrypt(s_val)
            
            self._engine._bind_and_execute("INSERT INTO queue_items (value, priority) VALUES (?, ?)", [st_val, int(priority)])
            self._persist()
            return "pushed"

    def pop(self):
        wtype = self.get_type()
        if wtype == "kv": raise TypeError("'pop' not supported on kv workspace")
        
        # Determine order
        order = "id ASC" # queue (FIFO)
        if wtype == "stack": order = "id DESC" # LIFO
        elif wtype == "priority_queue": order = "priority DESC, id ASC"
        
        self._engine._execute_raw("BEGIN IMMEDIATE TRANSACTION")
        try:
            results = self._engine._bind_and_fetch(f"SELECT id, value FROM queue_items ORDER BY {order} LIMIT 1", [])
            if not results:
                self._engine._execute_raw("COMMIT")
                return None
            
            id, st_val = results[0][0], results[0][1]
            val_str = self._security.decrypt(st_val)
            try: val = json.loads(val_str)
            except: val = val_str
            
            self._engine._bind_and_execute("DELETE FROM queue_items WHERE id = ?", [id])
            self._engine._execute_raw("COMMIT")
            self._persist()
            return val
        except Exception:
            self._engine._execute_raw("ROLLBACK")
            raise

    def peek(self):
        wtype = self.get_type()
        if wtype == "kv": raise TypeError("'peek' not supported on kv workspace")
        
        order = "id ASC"
        if wtype == "stack": order = "id DESC"
        elif wtype == "priority_queue": order = "priority DESC, id ASC"
        
        results = self._engine._bind_and_fetch(f"SELECT value FROM queue_items ORDER BY {order} LIMIT 1", [])
        if not results: return None
        
        val_str = self._security.decrypt(results[0][0])
        try: return json.loads(val_str)
        except: return val_str

    def push_many(self, list values, priority=0):
        wtype = self.get_type()
        if wtype == "kv":
            raise TypeError("Queue 'push_many' not supported in KV workspace")
            
        self._engine._execute_raw("BEGIN TRANSACTION")
        for val in values:
            s_val = json.dumps(val) if isinstance(val, (dict, list, bool, int, float)) else str(val)
            st_val = self._security.encrypt(s_val)
            self._engine._bind_and_execute("INSERT INTO queue_items (value, priority) VALUES (?, ?)", [st_val, int(priority)])
        self._engine._execute_raw("COMMIT")
        self._persist()
        return f"Pushed {len(values)} items"

    def pop_many(self, int count=1):
        wtype = self.get_type()
        if wtype == "kv": raise TypeError("'pop_many' not supported on kv workspace")
        
        order = "id ASC"
        if wtype == "stack": order = "id DESC"
        elif wtype == "priority_queue": order = "priority DESC, id ASC"
        
        results = self._engine._bind_and_fetch(f"SELECT id, value FROM queue_items ORDER BY {order} LIMIT ?", [count])
        if not results: return []
        
        ids = [row[0] for row in results]
        items = []
        for row in results:
            val_str = self._security.decrypt(row[1])
            try: items.append(json.loads(val_str))
            except: items.append(val_str)
            
        self._engine._execute_raw("BEGIN TRANSACTION")
        placeholders = ",".join(["?"] * len(ids))
        self._engine._bind_and_execute(f"DELETE FROM queue_items WHERE id IN ({placeholders})", ids)
        self._engine._execute_raw("COMMIT")
        self._persist()
        return items

    def count(self):
        wtype = self.get_type()
        if wtype == "kv":
            res = self._engine._bind_and_fetch("SELECT count(*) FROM kvstore WHERE key != '_sys_type'", [])
        else:
            res = self._engine._bind_and_fetch("SELECT count(*) FROM queue_items", [])
        return int(res[0][0])

    def clear(self):
        self._engine._execute_raw("DELETE FROM kvstore WHERE key != '_sys_type'")
        self._engine._execute_raw("DELETE FROM queue_items")
        self._cache.clear()
        self._persist()
        return "cleared"


    def remove(self, str key, value, ttl=None):
        data = self.getkey(key, deserialize=True)
        if not isinstance(data, list): raise TypeError("Not a list")
        if value in data:
            data.remove(value)
            return self.save(key, data, ttl=ttl)
        return "nochange"

    def delete(self, str key):
        k = key.lower().strip()
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
            self._persist()
            return "Deleted"
        except Exception as e:
            self._engine._execute_raw("ROLLBACK")
            raise e

    def search(self, str query, limit=100, deserialize=True, keys_only=False):
        if keys_only:
            sql = "SELECT kvstore.key FROM kvstore JOIN fts_kvstore ON kvstore.rowid = fts_kvstore.rowid WHERE fts_kvstore MATCH ? AND (kvstore.expires_at IS NULL OR kvstore.expires_at > datetime('now')) ORDER BY rank LIMIT ?"
        else:
            sql = "SELECT kvstore.key, kvstore.value FROM kvstore JOIN fts_kvstore ON kvstore.rowid = fts_kvstore.rowid WHERE fts_kvstore MATCH ? AND (kvstore.expires_at IS NULL OR kvstore.expires_at > datetime('now')) ORDER BY rank LIMIT ?"
        results = self._engine._bind_and_fetch(sql, [query, limit])
        if keys_only: return [row[0] for row in results]
        matches = {}
        for row in results:
            d_val = self._security.decrypt(row[1])
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
        res = self._audit.restore(key, timestamp)
        if isinstance(res, tuple) and res[0] == "value_ready":
            return self.patch(res[1] + res[3], res[2]) if res[3] else self.save(res[1], res[2])
        return res
    def restore_to(self, str ts):
        res = self._audit.restore_to(ts)
        self._cache.clear()
        self._persist()
        return res
    def compact(self, int retention_days=15): 
        res = self._audit.compact(retention_days)
        self._persist()
        return res
    def optimize_index(self): self._engine._execute_raw("INSERT INTO fts_kvstore(fts_kvstore) VALUES('optimize')")

    def rotate_master_key(self, new_key, old_key=None, dry_run=False, backup=False, batch=500, verify=True):
        if not new_key or not str(new_key).strip():
            raise ValueError("New master key is required")

        if old_key:
            old_sec = SecurityManager(old_key)
        else:
            old_sec = SecurityManager("")
        new_sec = SecurityManager(new_key)

        tables = ["kvstore", "audit_log", "archive"]
        enc_counts = []
        total_enc = 0

        for tbl in tables:
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

        rotated = 0
        try:
            if not dry_run:
                self._engine._execute_raw("BEGIN TRANSACTION")

            for tbl in tables:
                offset = 0
                while True:
                    rows = self._engine._bind_and_fetch(f"SELECT rowid, value FROM {tbl} LIMIT ? OFFSET ?", [batch, offset])
                    if not rows:
                        break
                    for row in rows:
                        if row[1] is None:
                            continue
                        val = str(row[1])
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
                self._persist()
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
        res = self._engine._bind_and_fetch("SELECT 1 FROM kvstore WHERE key = ? AND (expires_at IS NULL OR expires_at > datetime('now'))", [key.lower().strip()])
        return len(res) > 0

    def __iter__(self):
        res = self._engine._bind_and_fetch("SELECT key FROM kvstore WHERE (expires_at IS NULL OR expires_at > datetime('now'))", [])
        for row in res: yield row[0]

    def __len__(self):
        return self.count()

    def __getitem__(self, str k):
        v = self.getkey(k)
        if v == "Key not found": raise KeyError(k)
        return v
    def __setitem__(self, str k, v): self.save(k, v)
    def __delitem__(self, str k): 
        if self.delete(k) == "Key not found": raise KeyError(k)
