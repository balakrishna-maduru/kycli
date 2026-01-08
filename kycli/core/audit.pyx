# cython: language_level=3
from .engine cimport DatabaseEngine
from .security cimport SecurityManager
from .query cimport QueryEngine
import json
import os

cdef class AuditManager:
    def __init__(self, DatabaseEngine engine, SecurityManager security, QueryEngine query):
        self._engine = engine
        self._security = security
        self._query = query

    cpdef list get_history(self, str key=None):
        cdef str sql
        cdef list params = []
        if key and not key.startswith("-"):
            sql = "SELECT key, value, timestamp FROM audit_log WHERE key = ? ORDER BY id DESC"
            params = [key.lower().strip()]
        else:
            sql = "SELECT key, value, timestamp FROM audit_log ORDER BY id DESC"
        
        cdef list results = self._engine._bind_and_fetch(sql, params)
        cdef list final = []
        for row in results:
            final.append((row[0], self._security.decrypt(row[1]), row[2]))
        return final

    cpdef str restore(self, str key, timestamp=None):
        cdef str k = key.lower().strip()
        cdef str path = ""
        cdef str prefix = ""
        cdef int i = 0
        cdef list _results = []
        cdef str sql = ""
        cdef list params = []
        
        if "." in k or "[" in k:
            for i in range(len(k), 0, -1):
                prefix = k[:i]
                p_list = [prefix, prefix]
                _results = self._engine._bind_and_fetch("SELECT 1 FROM kvstore WHERE key = ? UNION SELECT 1 FROM audit_log WHERE key = ?", p_list)
                if _results:
                    path = k[i:]
                    k = prefix
                    break

        if path or timestamp:
            sql = "SELECT value FROM audit_log WHERE key = ?"
            params = [k]
            if timestamp:
                sql += " AND timestamp <= ? ORDER BY timestamp DESC LIMIT 1"
                params.append(timestamp)
            else:
                sql += " ORDER BY timestamp DESC LIMIT 1"
            
            _results = self._engine._bind_and_fetch(sql, params)
            if not _results:
                return f"No historical version found for key '{k}'"
            
            val = self._security.decrypt(_results[0][0])
            try:
                val = json.loads(val)
            except:
                pass
            
            if path:
                val = self._query.navigate(val, path)
                if isinstance(val, str) and (val.startswith("KeyError") or val.startswith("TypeError")):
                    return f"Error navigating history: {val}"
            
            return ("value_ready", k, val, path)

        _results = self._engine._bind_and_fetch("SELECT value FROM archive WHERE key = ? ORDER BY deleted_at DESC LIMIT 1", [k])
        if not _results:
            return "No archived version found for this key (Note: Archive is purged after 15 days)"
            
        cdef str latest_value = _results[0][0]
        _results = self._engine._bind_and_fetch("SELECT value FROM kvstore WHERE key = ?", [k])
        if _results and _results[0][0] == latest_value:
            return "Already in active store with identical value"
            
        self._engine._execute_raw("BEGIN TRANSACTION")
        self._engine._bind_and_execute("INSERT OR REPLACE INTO kvstore (key, value) VALUES (?, ?)", [k, latest_value])
        self._engine._bind_and_execute("INSERT INTO audit_log (key, value) VALUES (?, ?)", [k, latest_value])
        self._engine._execute_raw("COMMIT")
        return f"Restored: {k}"

    cpdef str restore_to(self, str timestamp):
        try:
            self._engine._execute_raw("BEGIN TRANSACTION")
            self._engine._execute_raw("DELETE FROM kvstore")
            self._engine._bind_and_execute("""
                INSERT INTO kvstore (key, value)
                SELECT key, value FROM (
                    SELECT key, value, MAX(timestamp) as ts 
                    FROM audit_log 
                    WHERE timestamp <= ?
                    GROUP BY key
                ) WHERE value IS NOT NULL
            """, [timestamp])
            self._engine._execute_raw("COMMIT")
            return f"🕒 Database restored to {timestamp}"
        except Exception as e:
            try: self._engine._execute_raw("ROLLBACK")
            except: pass
            raise RuntimeError(f"Restore failed: {e}")

    cpdef str compact(self, int retention_days=15):
        try:
            self._engine._execute_raw("BEGIN TRANSACTION")
            self._engine._bind_and_execute("DELETE FROM audit_log WHERE timestamp < DATETIME('now', '-' || ? || ' days')", [retention_days])
            self._engine._bind_and_execute("DELETE FROM archive WHERE deleted_at < DATETIME('now', '-15 days')", [])
            self._engine._execute_raw("COMMIT")
            self._engine._execute_raw("VACUUM")
            return "🧹 Compaction complete: Space reclaimed and stale history purged."
        except Exception as e:
            try: self._engine._execute_raw("ROLLBACK")
            except: pass
            raise RuntimeError(f"Compaction failed: {e}")
