# cython: language_level=3
from .sqlite_defs cimport *
import os

cdef class DatabaseEngine:
    def __init__(self, str db_path):
        self._data_path = db_path
        cdef bytes path_bytes = db_path.encode('utf-8')
        if sqlite3_open(path_bytes, &self._db) != SQLITE_OK:
            raise RuntimeError(f"Could not open database: {sqlite3_errmsg(self._db)}")
        
        # Optimizations
        self._execute_raw("PRAGMA journal_mode=WAL")
        self._execute_raw("PRAGMA synchronous=NORMAL")
        self._execute_raw("PRAGMA cache_size=-64000")
        self._execute_raw("PRAGMA temp_store=MEMORY")

    def __dealloc__(self):
        if self._db:
            sqlite3_close(self._db)
            self._db = NULL

    cpdef close(self):
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

    cdef _bind_and_execute(self, str sql, list params):
        cdef sqlite3_stmt* stmt = NULL
        cdef bytes sql_bytes = sql.encode('utf-8')
        if sqlite3_prepare_v2(self._db, sql_bytes, -1, &stmt, NULL) != SQLITE_OK:
            raise RuntimeError(f"Prepare error: {sqlite3_errmsg(self._db)}")
        
        cdef bytes p_bytes
        for i, p in enumerate(params):
            if p is None:
                sqlite3_bind_null(stmt, i + 1)
            else:
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
            if p is None:
                sqlite3_bind_null(stmt, i + 1)
            else:
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
