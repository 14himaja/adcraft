import base64

import pytest
from cryptography.exceptions import InvalidTag

from app.security.crypto import decrypt_token, encrypt_token

KEY = base64.b64encode(bytes(range(32))).decode()
OTHER_KEY = base64.b64encode(bytes(range(1, 33))).decode()


def test_roundtrip():
    assert decrypt_token(KEY, encrypt_token(KEY, "EAABtoken")) == "EAABtoken"


def test_ciphertext_hides_plaintext_and_differs_each_time():
    a, b = encrypt_token(KEY, "EAABtoken"), encrypt_token(KEY, "EAABtoken")
    assert a != b
    assert b"EAABtoken" not in a


def test_tampered_ciphertext_is_rejected():
    blob = bytearray(encrypt_token(KEY, "EAABtoken"))
    blob[-1] ^= 1
    with pytest.raises(InvalidTag):
        decrypt_token(KEY, bytes(blob))


def test_wrong_key_is_rejected():
    with pytest.raises(InvalidTag):
        decrypt_token(OTHER_KEY, encrypt_token(KEY, "EAABtoken"))


def test_key_must_be_32_bytes():
    with pytest.raises(ValueError):
        encrypt_token(base64.b64encode(bytes(16)).decode(), "x")
