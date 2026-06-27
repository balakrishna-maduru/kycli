# cython: language_level=3
from .sqlite_defs cimport *
import os
import time

cdef int _RETRY_ATTEMPTS = 3
cdef int _RETRY_BASE_MS = 25

cdef bint _is_retryable_error(str msg):
    if not msg:
        return False
    m = msg.lower()
    return "locked" in m or "busy" in m

cdef void _retry_sleep(int attempt):
    # Short exponential backoff to fail fast but still handle transient locks.
    delay_ms = _RETRY_BASE_MS * (2 ** attempt)
    time.sleep(delay_ms / 1000.0)

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
        cdef int attempt = 0
        cdef int rc
        while True:
            rc = sqlite3_exec(self._db, sql_bytes, NULL, NULL, &errmsg)
            if rc == SQLITE_OK:
                return 0
            msg = errmsg.decode('utf-8') if errmsg else "Unknown error"
            if attempt >= _RETRY_ATTEMPTS - 1 or not _is_retryable_error(msg):
                raise RuntimeError(f"SQLite error: {msg}")
            _retry_sleep(attempt)
            attempt += 1

    cdef _bind_and_execute(self, str sql, list params):
        cdef sqlite3_stmt* stmt = NULL
        cdef bytes sql_bytes = sql.encode('utf-8')
        cdef bytes p_bytes
        cdef int attempt = 0
        cdef int rc
        cdef const char* err_ptr
        cdef str err
        while True:
            if sqlite3_prepare_v2(self._db, sql_bytes, -1, &stmt, NULL) != SQLITE_OK:
                err_ptr = sqlite3_errmsg(self._db)
                err = err_ptr.decode('utf-8') if err_ptr != NULL else "Unknown error"
                if attempt >= _RETRY_ATTEMPTS - 1 or not _is_retryable_error(err):
                    raise RuntimeError(f"Prepare error: {err}")
                _retry_sleep(attempt)
                attempt += 1
                continue

            for i, p in enumerate(params):
                if p is None:
                    sqlite3_bind_null(stmt, i + 1)
                else:
                    p_bytes = str(p).encode('utf-8')
                    sqlite3_bind_text(stmt, i + 1, p_bytes, len(p_bytes), SQLITE_TRANSIENT)

            rc = sqlite3_step(stmt)
            if rc == SQLITE_DONE:
                sqlite3_finalize(stmt)
                return

            err_ptr = sqlite3_errmsg(self._db)
            err = err_ptr.decode('utf-8') if err_ptr != NULL else "Unknown error"
            sqlite3_finalize(stmt)
            if attempt >= _RETRY_ATTEMPTS - 1 or not _is_retryable_error(err):
                raise RuntimeError(f"Step error: {err}")
            _retry_sleep(attempt)
            attempt += 1

    cdef list _bind_and_fetch(self, str sql, list params):
        cdef sqlite3_stmt* stmt = NULL
        cdef bytes sql_bytes = sql.encode('utf-8')
        cdef bytes p_bytes
        cdef int attempt = 0
        cdef int rc
        cdef const char* err_ptr
        cdef str err
        cdef list rows
        cdef int col_count
        cdef list row
        cdef const unsigned char* text

        while True:
            if sqlite3_prepare_v2(self._db, sql_bytes, -1, &stmt, NULL) != SQLITE_OK:
                err_ptr = sqlite3_errmsg(self._db)
                err = err_ptr.decode('utf-8') if err_ptr != NULL else "Unknown error"
                if attempt >= _RETRY_ATTEMPTS - 1 or not _is_retryable_error(err):
                    raise RuntimeError(f"Prepare error: {err}")
                _retry_sleep(attempt)
                attempt += 1
                continue

            for i, p in enumerate(params):
                if p is None:
                    sqlite3_bind_null(stmt, i + 1)
                else:
                    p_bytes = str(p).encode('utf-8')
                    sqlite3_bind_text(stmt, i + 1, p_bytes, len(p_bytes), SQLITE_TRANSIENT)

            rows = []
            while True:
                rc = sqlite3_step(stmt)
                if rc == SQLITE_ROW:
                    col_count = sqlite3_column_count(stmt)
                    row = []
                    for i in range(col_count):
                        text = sqlite3_column_text(stmt, i)
                        if text == NULL:
                            row.append(None)
                        else:
                            row.append((<char*>text).decode('utf-8'))
                    rows.append(row)
                    continue

                if rc == SQLITE_DONE:
                    sqlite3_finalize(stmt)
                    return rows

                err_ptr = sqlite3_errmsg(self._db)
                err = err_ptr.decode('utf-8') if err_ptr != NULL else "Unknown error"
                sqlite3_finalize(stmt)
                if attempt >= _RETRY_ATTEMPTS - 1 or not _is_retryable_error(err):
                    raise RuntimeError(f"Step error: {err}")
                _retry_sleep(attempt)
                attempt += 1
                break
