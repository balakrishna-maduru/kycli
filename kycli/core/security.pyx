# cython: language_level=3
import os
import base64
import hashlib
import secrets
try:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except ImportError:
    AESGCM = None

cdef bytes _MASTER_KEY_SALT = b'kycli_vault_salt'
cdef bytes _TOKEN_SALT = b'kycli_token_salt'


cdef bytes _derive_key_bytes(str secret, bytes salt):
    cdef object kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
    )
    return kdf.derive(secret.encode('utf-8'))

cdef class SecurityManager:
    def __init__(self, str master_key=None):
        self._master_key = master_key
        self._aesgcm = None
        if master_key:
            if AESGCM is None:
                raise ImportError("cryptography library is required for encryption. Install it with 'pip install cryptography'.")

            key = _derive_key_bytes(master_key, _MASTER_KEY_SALT)
            self._aesgcm = AESGCM(key)

    cpdef str encrypt(self, str plaintext):
        if self._aesgcm is None:
            return plaintext
        nonce = os.urandom(12)
        ciphertext = self._aesgcm.encrypt(nonce, plaintext.encode('utf-8'), None)
        return "enc:" + base64.b64encode(nonce + ciphertext).decode('utf-8')

    cpdef str decrypt(self, str encrypted_text):
        if encrypted_text is None:
            return "[DELETED]"
        t_val = encrypted_text.strip()
        if not t_val.startswith("enc:"):
            return t_val
        if self._aesgcm is None:
            return "[ENCRYPTED: Provide a master key to view this value]"
        try:
            data = base64.b64decode(t_val[4:].encode('utf-8'))
            nonce = data[:12]
            ciphertext = data[12:]
            return self._aesgcm.decrypt(nonce, ciphertext, None).decode('utf-8')
        except Exception:
            return "[DECRYPTION FAILED: Incorrect master key]"

    cpdef bytes encrypt_blob(self, bytes blob):
        if self._aesgcm is None or blob is None:
            return blob
        nonce = os.urandom(12)
        ciphertext = self._aesgcm.encrypt(nonce, blob, None)
        # Format: <Nonce:12><Ciphertext>
        return nonce + ciphertext

    cpdef bytes decrypt_blob(self, bytes encrypted_blob):
        if self._aesgcm is None:
            return encrypted_blob 
        if len(encrypted_blob) < 12:
             # Not enough data for nonce, maybe it's unencrypted or corrupted
             # Check header? The caller handles file header. Here we just decrypt payload.
             raise ValueError("Invalid blob length")
        
        try:
            nonce = encrypted_blob[:12]
            ciphertext = encrypted_blob[12:]
            return self._aesgcm.decrypt(nonce, ciphertext, None)
        except Exception:
             raise ValueError("Decryption failed: Incorrect master key or corrupted data")

    cpdef str hash_token(self, str token):
        if token is None:
            raise ValueError("Token is required")
        return hashlib.sha256(_TOKEN_SALT + token.encode('utf-8')).hexdigest()

    cpdef bint verify_token(self, str token, str expected_hash):
        if not token or not expected_hash:
            return False
        try:
            return secrets.compare_digest(self.hash_token(token), expected_hash)
        except Exception:
            return False

    cpdef str generate_token(self):
        return secrets.token_urlsafe(24)
