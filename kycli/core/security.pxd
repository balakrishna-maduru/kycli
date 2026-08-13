# cython: language_level=3

cdef class SecurityManager:
    cdef object _aesgcm
    cdef str _master_key
    cpdef str encrypt(self, str plaintext)
    cpdef str decrypt(self, str encrypted_text)
    cpdef bytes encrypt_blob(self, bytes blob)
    cpdef bytes decrypt_blob(self, bytes encrypted_blob)
    cpdef str hash_token(self, str token)
    cpdef bint verify_token(self, str token, str expected_hash)
    cpdef str generate_token(self)
