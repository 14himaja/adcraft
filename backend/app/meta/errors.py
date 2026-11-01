from enum import StrEnum

from tenacity import AsyncRetrying, retry_if_exception, stop_after_attempt, wait_exponential_jitter

from app.errors import AppError

WRITE_ATTEMPTS = 3
DEFAULT_WAIT = wait_exponential_jitter(initial=1, max=30)
THROTTLE_CODES = frozenset({4, 17, 32, 613, *range(80000, 80015)})
TRANSIENT_CODES = frozenset({1, 2})


class ErrorClass(StrEnum):
    RETRYABLE = "RETRYABLE"
    AUTH = "AUTH"
    INVALID = "INVALID"
    PERMISSION = "PERMISSION"
    UNKNOWN = "UNKNOWN"


class MetaError(AppError):
    status, code = 502, "META_ERROR"

    def __init__(
        self,
        *,
        http_status: int | None = None,
        meta_code: int | None = None,
        meta_subcode: int | None = None,
        message: str = "Meta API error",
        user_msg: str | None = None,
        retry_after_s: float | None = None,
    ):
        super().__init__(user_msg or message, {"meta_code": meta_code, "meta_subcode": meta_subcode})
        self.http_status = http_status
        self.meta_code = meta_code
        self.meta_subcode = meta_subcode
        self.meta_message = message
        self.user_msg = user_msg
        self.retry_after_s = retry_after_s


class MetaAuthExpired(AppError):
    status, code = 409, "META_AUTH_EXPIRED"


def meta_error_from_body(body: dict | None, http_status: int | None) -> MetaError:
    error = (body or {}).get("error") or {}
    return MetaError(
        http_status=http_status,
        meta_code=error.get("code"),
        meta_subcode=error.get("error_subcode"),
        message=error.get("message") or "Meta API error",
        user_msg=error.get("error_user_msg"),
    )


def classify(err: MetaError) -> ErrorClass:
    code = err.meta_code
    if code == 190:
        return ErrorClass.AUTH
    if code in THROTTLE_CODES or code in TRANSIENT_CODES:
        return ErrorClass.RETRYABLE
    if code == 10 or (code is not None and 200 <= code <= 299):
        return ErrorClass.PERMISSION
    if code == 100:
        return ErrorClass.INVALID
    if (err.http_status or 0) >= 500:
        return ErrorClass.RETRYABLE
    return ErrorClass.UNKNOWN


def is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return True
    return isinstance(exc, MetaError) and classify(exc) == ErrorClass.RETRYABLE


async def with_retries(fn, *args, wait=DEFAULT_WAIT, counter: list[int] | None = None):
    """`await fn(*args)`, retrying only `is_retryable` errors (never INVALID/AUTH/PERMISSION)."""
    async for attempt in AsyncRetrying(
        stop=stop_after_attempt(WRITE_ATTEMPTS),
        wait=wait,
        retry=retry_if_exception(is_retryable),
        reraise=True,
    ):
        with attempt:
            if counter is not None:
                counter[0] += 1
            return await fn(*args)
    raise AssertionError("unreachable")
