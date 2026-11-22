import time
from collections.abc import Callable
from typing import Annotated, Any

from bson import ObjectId
from fastapi import Depends, Request

from app.config import Settings
from app.errors import RateLimited, Unauthenticated
from app.security.jwt import InvalidToken, decode_token

SESSION_COOKIE = "session"


def get_db(request: Request):
    return request.app.state.db


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings


async def current_user(
    request: Request,
    db: Annotated[Any, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> dict:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise Unauthenticated("Not logged in")
    try:
        claims = decode_token(token, settings.jwt_secret)
    except InvalidToken as exc:
        raise Unauthenticated("Session expired, please log in again") from exc
    user = await db.users.find_one({"_id": ObjectId(claims["sub"])})
    if user is None:
        raise Unauthenticated("Not logged in")
    return user


async def optional_user(
    request: Request,
    db: Annotated[Any, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> dict | None:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    try:
        claims = decode_token(token, settings.jwt_secret)
    except InvalidToken:
        return None
    try:
        return await db.users.find_one({"_id": ObjectId(claims["sub"])})
    except Exception:
        return None


class RateLimiter:
    """Fixed window per key.
    ponytail: in-process, single instance only; move to a shared store if the API is scaled out."""

    def __init__(self, limit: int, window_s: float, clock: Callable[[], float] = time.monotonic):
        self.limit, self.window_s, self._clock = limit, window_s, clock
        self._windows: dict[str, tuple[float, int]] = {}

    def hit(self, key: str) -> None:
        now = self._clock()
        start, count = self._windows.get(key, (now, 0))
        if now - start >= self.window_s:
            start, count = now, 0
        if count >= self.limit:
            raise RateLimited(
                "Too many attempts, try again later",
                {"retry_after_s": round(self.window_s - (now - start))},
            )
        self._windows[key] = (start, count + 1)


def get_container(request: Request) -> "Container":
    return request.app.state.container


from app.container import Container  # noqa: E402

DbDep = Annotated[Any, Depends(get_db)]
SettingsDep = Annotated[Settings, Depends(get_settings_dep)]
UserDep = Annotated[dict, Depends(current_user)]
OptionalUserDep = Annotated[dict | None, Depends(optional_user)]
ContainerDep = Annotated[Container, Depends(get_container)]
