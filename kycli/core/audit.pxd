# cython: language_level=3
from .engine cimport DatabaseEngine
from .security cimport SecurityManager
from .query cimport QueryEngine

cdef class AuditManager:
    cdef DatabaseEngine _engine
    cdef SecurityManager _security
    cdef QueryEngine _query
    
    cpdef list get_history(self, str key=*)
    cpdef restore(self, str key, timestamp=*)
    cpdef str restore_to(self, str timestamp)
    cpdef str compact(self, int retention_days=*)
