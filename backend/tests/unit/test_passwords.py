from app.security.passwords import hash_password, verify_password


def test_hash_is_not_the_password_and_verifies():
    hashed = hash_password("correct horse battery")
    assert hashed != "correct horse battery"
    assert verify_password(hashed, "correct horse battery")


def test_wrong_password_is_false():
    assert not verify_password(hash_password("correct horse battery"), "wrong")


def test_same_password_hashes_differently():
    assert hash_password("same password!") != hash_password("same password!")


def test_garbage_hash_is_false_not_error():
    assert not verify_password("not-a-hash", "anything")
