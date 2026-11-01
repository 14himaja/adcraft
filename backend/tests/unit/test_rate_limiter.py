import pytest

from app.api.deps import RateLimiter
from app.errors import RateLimited


def test_blocks_after_limit_and_resets_after_window():
    now = [0.0]
    limiter = RateLimiter(limit=2, window_s=60, clock=lambda: now[0])
    limiter.hit("ip")
    limiter.hit("ip")
    with pytest.raises(RateLimited):
        limiter.hit("ip")
    now[0] = 61.0
    limiter.hit("ip")  # new window


def test_keys_are_independent():
    limiter = RateLimiter(limit=1, window_s=60, clock=lambda: 0.0)
    limiter.hit("a")
    limiter.hit("b")
