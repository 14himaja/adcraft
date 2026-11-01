import pytest

from app.security.jwt import InvalidToken, decode_token, issue_token

SECRET = "x" * 32


def test_roundtrip_returns_subject():
    assert decode_token(issue_token("user-1", SECRET), SECRET)["sub"] == "user-1"


def test_extra_claims_are_kept():
    assert decode_token(issue_token("u", SECRET, extra={"nonce": "n1"}), SECRET)["nonce"] == "n1"


def test_expired_token_is_rejected():
    with pytest.raises(InvalidToken):
        decode_token(issue_token("user-1", SECRET, ttl_minutes=-1), SECRET)


def test_token_signed_with_other_secret_is_rejected():
    with pytest.raises(InvalidToken):
        decode_token(issue_token("user-1", "y" * 32), SECRET)


def test_garbage_token_is_rejected():
    with pytest.raises(InvalidToken):
        decode_token("not.a.jwt", SECRET)
