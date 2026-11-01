from datetime import UTC, datetime, timedelta
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...


def utcnow() -> datetime:
    return datetime.now(UTC)


class SystemClock:
    def now(self) -> datetime:
        return utcnow()


class FixedClock:
    def __init__(self, start: datetime):
        if start.tzinfo is None:
            raise ValueError("FixedClock needs a timezone-aware datetime")
        self._now = start

    def now(self) -> datetime:
        return self._now

    def advance(self, **kwargs) -> None:
        self._now += timedelta(**kwargs)
