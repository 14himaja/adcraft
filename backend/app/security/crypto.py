import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_NONCE_BYTES = 12


def _key(key_b64: str) -> bytes:
    key = base64.b64decode(key_b64)
    if len(key) != 32:
        raise ValueError("TOKEN_ENCRYPTION_KEY must be base64 of exactly 32 bytes")
    return key


def encrypt_token(key_b64: str, plaintext: str) -> bytes:
    nonce = os.urandom(_NONCE_BYTES)
    return nonce + AESGCM(_key(key_b64)).encrypt(nonce, plaintext.encode(), None)


def decrypt_token(key_b64: str, blob: bytes) -> str:
    nonce, ciphertext = blob[:_NONCE_BYTES], blob[_NONCE_BYTES:]
    return AESGCM(_key(key_b64)).decrypt(nonce, ciphertext, None).decode()
