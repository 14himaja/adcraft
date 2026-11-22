import asyncio
import re
from collections.abc import Awaitable, Callable
from typing import TypeVar

import httpx

from app.errors import AppError

T = TypeVar("T")

_SECRET_RE = re.compile(
    r"(access_token|refresh_token|client_secret|authorization|bearer\s+)[^\s&\"']+",
    re.IGNORECASE,
)


def sanitize_error_message(message: str, max_len: int = 320) -> str:
    """Redact potential secret tokens before logging or returning messages to clients."""
    cleaned = _SECRET_RE.sub(r"\1[REDACTED]", message or "")
    return cleaned[:max_len]


class InvalidOAuthState(AppError):
    status, code = 400, "INVALID_OAUTH_STATE"


class IntegrationNotConfigured(AppError):
    status, code = 409, "PLATFORM_NOT_CONFIGURED"


class IntegrationNotConnected(AppError):
    status, code = 409, "PLATFORM_NOT_CONNECTED"


class IntegrationAuthExpired(AppError):
    status, code = 409, "PLATFORM_AUTH_EXPIRED"


class IntegrationPermissionDenied(AppError):
    status, code = 403, "PLATFORM_PERMISSION_DENIED"


class IntegrationRateLimited(AppError):
    status, code = 429, "PLATFORM_RATE_LIMITED"


class IntegrationValidationError(AppError):
    status, code = 422, "PLATFORM_VALIDATION_FAILED"


class IntegrationApiError(AppError):
    status, code = 502, "PLATFORM_API_ERROR"

    def __init__(
        self,
        message: str = "Platform API error",
        *,
        platform: str = "",
        http_status: int | None = None,
        retryable: bool = False,
        details: dict | None = None,
    ):
        super().__init__(
            sanitize_error_message(message),
            {"platform": platform, "http_status": http_status, **(details or {})},
        )
        self.platform = platform
        self.http_status = http_status
        self.retryable = retryable


def is_transient_integration_error(exc: BaseException) -> bool:
    """Retry only transient network/timeout/5xx/rate-limit failures, never auth or validation."""
    if isinstance(exc, (TimeoutError, ConnectionError, httpx.TimeoutException, httpx.ConnectError)):
        return True
    if isinstance(exc, IntegrationRateLimited):
        return True
    return isinstance(exc, IntegrationApiError) and exc.retryable


async def with_integration_retries(
    fn: Callable[..., Awaitable[T]],
    *args,
    attempts: int = 3,
    wait=None,
    **kwargs,
) -> T:
    for attempt_idx in range(1, attempts + 1):
        try:
            return await fn(*args, **kwargs)
        except Exception as exc:
            if not is_transient_integration_error(exc) or attempt_idx >= attempts:
                raise
            if wait is not None:
                try:
                    delay = float(wait(None)) if callable(wait) else float(wait)
                except Exception:
                    delay = 0.0
            else:
                delay = min(0.5 * (2 ** (attempt_idx - 1)), 8.0)
            if delay > 0:
                await asyncio.sleep(delay)
    raise AssertionError("unreachable")
