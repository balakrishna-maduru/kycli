# cython: language_level=3

cdef class SecurityManager:
    cdef object _aesgcm
    cdef str _master_key
    cdef str encrypt(self, str plaintext)
    cdef str decrypt(self, str encrypted_text)
