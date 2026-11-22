from typing import Any

import httpx

from app.integrations.base.errors import (
    IntegrationApiError,
    IntegrationAuthExpired,
    IntegrationPermissionDenied,
    IntegrationRateLimited,
    sanitize_error_message,
    with_integration_retries,
)


def _extract_error_message(body: Any, fallback: str) -> str:
    if isinstance(body, dict):
        if isinstance(body.get("error"), dict):
            err = body["error"]
            return err.get("message") or err.get("error_description") or fallback
        return (
            body.get("error_description")
            or body.get("message")
            or body.get("detail")
            or body.get("error")
            or fallback
        )
    return fallback


async def platform_request(
    platform: str,
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
    json: Any = None,
    data: Any = None,
    content: bytes | None = None,
    auth: tuple[str, str] | None = None,
    timeout_s: float = 15.0,
    retry_transient: bool = True,
) -> dict[str, Any]:
    """Execute an HTTP request against an official platform API with normalized error handling."""

    async def _send() -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=timeout_s) as client:
                response = await client.request(
                    method,
                    url,
                    headers=headers,
                    params=params,
                    json=json,
                    data=data,
                    content=content,
                    auth=auth,
                )
        except (httpx.TimeoutException, TimeoutError) as exc:
            raise IntegrationApiError(
                f"{platform.title()} API request timed out",
                platform=platform,
                retryable=True,
            ) from exc
        except (httpx.ConnectError, ConnectionError) as exc:
            raise IntegrationApiError(
                f"Could not reach {platform.title()} API",
                platform=platform,
                retryable=True,
            ) from exc

        try:
            parsed = response.json() if response.content else {}
        except ValueError:
            parsed = {"raw": response.text[:300]}

        if 200 <= response.status_code < 300:
            return parsed if isinstance(parsed, dict) else {"data": parsed}

        msg = sanitize_error_message(_extract_error_message(parsed, f"{platform.title()} HTTP {response.status_code}"))
        if response.status_code == 401:
            raise IntegrationAuthExpired(
                f"{platform.title()} authorization expired or was revoked. Please reconnect.",
                {"platform": platform, "reason": msg},
            )
        if response.status_code == 403:
            raise IntegrationPermissionDenied(
                f"{platform.title()} denied permission: {msg}",
                {"platform": platform, "reason": msg},
            )
        if response.status_code == 429:
            retry_after = response.headers.get("retry-after") or response.headers.get("x-ratelimit-reset")
            raise IntegrationRateLimited(
                f"{platform.title()} rate limit reached. Try again shortly.",
                {"platform": platform, "retry_after": retry_after},
            )
        if response.status_code >= 500:
            raise IntegrationApiError(
                f"{platform.title()} service unavailable ({response.status_code}): {msg}",
                platform=platform,
                http_status=response.status_code,
                retryable=True,
            )
        raise IntegrationApiError(
            f"{platform.title()} rejected the request: {msg}",
            platform=platform,
            http_status=response.status_code,
            retryable=False,
        )

    if retry_transient:
        return await with_integration_retries(_send)
    return await _send()
