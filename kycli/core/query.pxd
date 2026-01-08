# cython: language_level=3

cdef class QueryEngine:
    cpdef navigate(self, data, str path)
    cpdef patch_value(self, data, str path, value)
