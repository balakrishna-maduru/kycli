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
from datetime import datetime, timedelta, timezone
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

    def __init__(self, db_path=None, schema=None, master_key=None, cache_size=1000):
        if db_path is None:
            db_path = os.path.expanduser("~/kydata.db")
        
        dir_name = os.path.dirname(db_path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)

        self._engine = DatabaseEngine(db_path)
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

        # TTL Cleanup: Move expired keys to archive before deleting
        self._engine._execute_raw("""
            INSERT INTO archive (key, value)
            SELECT key, value FROM kvstore 
            WHERE expires_at IS NOT NULL AND expires_at < datetime('now')
        """)
        self._engine._execute_raw("DELETE FROM kvstore WHERE expires_at IS NOT NULL AND expires_at < datetime('now')")

    def __enter__(self):
        return self

    @property
    def data_path(self): return self._engine._data_path

    def __exit__(self, et, ev, tb):
        self._engine.close()

    def _encrypt(self, str val): return self._security.encrypt(val)
    def _decrypt(self, str val): return self._security.decrypt(val)

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
                matches[row[0]] = json.loads(d_val) if deserialize else d_val
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

    def push(self, str key, value, unique=False, ttl=None):
        data = self.getkey(key, deserialize=True)
        if data == "Key not found": data = []
        if not isinstance(data, list): raise TypeError("Not a list")
        if unique and value in data: return "nochange"
        data.append(value)
        return self.save(key, data, ttl=ttl)

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
        return res
    def compact(self, int retention_days=15): return self._audit.compact(retention_days)
    def optimize_index(self): self._engine._execute_raw("INSERT INTO fts_kvstore(fts_kvstore) VALUES('optimize')")

    def __contains__(self, str key):
        res = self._engine._bind_and_fetch("SELECT 1 FROM kvstore WHERE key = ? AND (expires_at IS NULL OR expires_at > datetime('now'))", [key.lower().strip()])
        return len(res) > 0

    def __iter__(self):
        res = self._engine._bind_and_fetch("SELECT key FROM kvstore WHERE (expires_at IS NULL OR expires_at > datetime('now'))", [])
        for row in res: yield row[0]

    def __len__(self):
        res = self._engine._bind_and_fetch("SELECT COUNT(*) FROM kvstore WHERE (expires_at IS NULL OR expires_at > datetime('now'))", [])
        return int(res[0][0]) if res else 0

    def __getitem__(self, str k):
        v = self.getkey(k)
        if v == "Key not found": raise KeyError(k)
        return v
    def __setitem__(self, str k, v): self.save(k, v)
    def __delitem__(self, str k): 
        if self.delete(k) == "Key not found": raise KeyError(k)
