from datetime import timedelta

import jwt

from app.clock import utcnow


class InvalidToken(Exception):
    pass


def issue_token(subject: str, secret: str, ttl_minutes: int = 720, *, extra: dict | None = None) -> str:
    now = utcnow()
    claims = {"sub": subject, "iat": now, "exp": now + timedelta(minutes=ttl_minutes), **(extra or {})}
    return jwt.encode(claims, secret, algorithm="HS256")


def decode_token(token: str, secret: str) -> dict:
    try:
        return jwt.decode(token, secret, algorithms=["HS256"], options={"require": ["exp", "sub"]})
    except jwt.PyJWTError as exc:
        raise InvalidToken(str(exc)) from exc
