# cython: language_level=3

cdef class SecurityManager:
    cdef object _aesgcm
    cdef str _master_key
    cdef str encrypt(self, str plaintext)
    cdef str decrypt(self, str encrypted_text)
    cdef bytes encrypt_blob(self, bytes blob)
    cdef bytes decrypt_blob(self, bytes encrypted_blob)
