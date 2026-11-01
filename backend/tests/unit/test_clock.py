from datetime import UTC, datetime, timedelta

import pytest

from app.clock import FixedClock, SystemClock, utcnow


def test_system_clock_is_timezone_aware():
    assert SystemClock().now().tzinfo is not None
    assert utcnow().tzinfo is not None


def test_fixed_clock_returns_start_and_advances():
    start = datetime(2026, 10, 6, 9, 0, tzinfo=UTC)
    clock = FixedClock(start)
    assert clock.now() == start
    clock.advance(days=7, hours=1)
    assert clock.now() == start + timedelta(days=7, hours=1)


def test_fixed_clock_rejects_naive_datetime():
    with pytest.raises(ValueError):
        FixedClock(datetime(2026, 10, 6))
