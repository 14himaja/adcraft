import pytest

from app.errors import AppError
from app.meta.errors import (
    ErrorClass,
    MetaAuthExpired,
    MetaError,
    classify,
    is_retryable,
    meta_error_from_body,
)
from tests.meta_payloads import m0


def err(code=None, http_status=400, subcode=None):
    return MetaError(http_status=http_status, meta_code=code, meta_subcode=subcode)


@pytest.mark.parametrize("code", [4, 17, 32, 613, 80000, 80004, 80014, 1, 2])
def test_throttle_and_transient_codes_are_retryable(code):
    assert classify(err(code)) == ErrorClass.RETRYABLE


def test_190_is_auth():
    assert classify(err(190)) == ErrorClass.AUTH


@pytest.mark.parametrize("code", [10, 200, 294, 299])
def test_permission_codes(code):
    assert classify(err(code)) == ErrorClass.PERMISSION


def test_100_is_invalid_and_keeps_subcode_and_user_message():
    error = meta_error_from_body(m0("r6_campaign_missing_budget_sharing.response"), 400)
    assert classify(error) == ErrorClass.INVALID
    assert error.meta_code == 100 and error.meta_subcode == 4834011
    assert error.user_msg is not None and "is_adset_budget_sharing_enabled" in error.user_msg


def test_server_error_without_code_is_retryable():
    assert classify(err(None, http_status=503)) == ErrorClass.RETRYABLE


def test_unknown_code_is_unknown():
    assert classify(err(12345)) == ErrorClass.UNKNOWN


def test_envelope_uses_meta_user_message():
    error = meta_error_from_body(m0("r6_campaign_missing_budget_sharing.response"), 400)
    assert error.status == 502 and error.code == "META_ERROR"
    assert error.message.startswith("You must specify True or False")
    assert error.details == {"meta_code": 100, "meta_subcode": 4834011}


def test_body_without_error_object_still_builds_an_error():
    assert meta_error_from_body({}, 500).meta_code is None


@pytest.mark.parametrize(
    "exc,expected",
    [
        (TimeoutError(), True),
        (ConnectionError(), True),
        (err(17), True),
        (err(100), False),
        (err(190), False),
        (ValueError(), False),
    ],
)
def test_is_retryable_predicate_matches_table(exc, expected):
    assert is_retryable(exc) is expected


def test_meta_auth_expired():
    expired = MetaAuthExpired()
    assert isinstance(expired, AppError)
    assert expired.status == 409
    assert expired.code == "META_AUTH_EXPIRED"


async def test_with_retries_retries_only_retryable_errors_three_times():
    from tenacity import wait_none

    from app.meta.errors import with_retries

    calls = []

    async def flaky(fail_with):
        calls.append(1)
        raise fail_with

    with pytest.raises(TimeoutError):
        await with_retries(flaky, TimeoutError(), wait=wait_none())
    assert len(calls) == 3
    calls.clear()
    with pytest.raises(MetaError):
        await with_retries(flaky, err(100), wait=wait_none())
    assert len(calls) == 1


async def test_with_retries_counts_attempts():
    from tenacity import wait_none

    from app.meta.errors import with_retries

    outcomes = [TimeoutError(), "ok"]

    async def call():
        outcome = outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    counter = [0]
    assert await with_retries(call, wait=wait_none(), counter=counter) == "ok"
    assert counter == [2]
