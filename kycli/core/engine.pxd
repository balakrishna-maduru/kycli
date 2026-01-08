# cython: language_level=3
from .sqlite_defs cimport *

cdef class DatabaseEngine:
    cdef sqlite3* _db
    cdef str _data_path
    cdef int _execute_raw(self, str sql) except -1
    cdef _bind_and_execute(self, str sql, list params)
    cdef list _bind_and_fetch(self, str sql, list params)
    cpdef close(self)
