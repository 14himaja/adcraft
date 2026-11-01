import logging
import re
import uuid
from contextvars import ContextVar

import structlog

correlation_id_var: ContextVar[str | None] = ContextVar("correlation_id", default=None)
_SAFE_ID = re.compile(r"[A-Za-z0-9-]{1,64}")


class CorrelationIdMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        incoming = dict(scope["headers"]).get(b"x-correlation-id", b"").decode("latin-1")
        cid = incoming if _SAFE_ID.fullmatch(incoming) else uuid.uuid4().hex
        token = correlation_id_var.set(cid)

        async def send_with_header(message):
            if message["type"] == "http.response.start":
                message.setdefault("headers", []).append((b"x-correlation-id", cid.encode()))
            await send(message)

        try:
            await self.app(scope, receive, send_with_header)
        finally:
            correlation_id_var.reset(token)


def add_correlation_id(logger, method, event: dict) -> dict:
    cid = correlation_id_var.get()
    if cid:
        event["correlation_id"] = cid
    return event


def configure_logging(app_env: str) -> None:
    renderer = (
        structlog.dev.ConsoleRenderer() if app_env == "development" else structlog.processors.JSONRenderer()
    )
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            add_correlation_id,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    )
