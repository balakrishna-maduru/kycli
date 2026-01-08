# cython: language_level=3
import os
import base64
try:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except ImportError:
    AESGCM = None

cdef class SecurityManager:
    def __init__(self, str master_key=None):
        self._master_key = master_key
        self._aesgcm = None
        if master_key:
            if AESGCM is None:
                raise ImportError("cryptography library is required for encryption. Install it with 'pip install cryptography'.")
            
            salt = b'kycli_vault_salt' 
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=100000,
            )
            key = kdf.derive(master_key.encode('utf-8'))
            self._aesgcm = AESGCM(key)

    cdef str encrypt(self, str plaintext):
        if self._aesgcm is None:
            return plaintext
        nonce = os.urandom(12)
        ciphertext = self._aesgcm.encrypt(nonce, plaintext.encode('utf-8'), None)
        return "enc:" + base64.b64encode(nonce + ciphertext).decode('utf-8')

    cdef str decrypt(self, str encrypted_text):
        if encrypted_text is None:
            return "[DELETED]"
        if not encrypted_text.startswith("enc:"):
            return encrypted_text
        if self._aesgcm is None:
            return "[ENCRYPTED: Provide a master key to view this value]"
        try:
            data = base64.b64decode(encrypted_text[4:].encode('utf-8'))
            nonce = data[:12]
            ciphertext = data[12:]
            return self._aesgcm.decrypt(nonce, ciphertext, None).decode('utf-8')
        except Exception:
            return "[DECRYPTION FAILED: Incorrect master key]"
