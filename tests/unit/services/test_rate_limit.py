from datetime import UTC, datetime, timedelta

from app.services.rate_limit import SlidingWindowRateLimiter


def test_rate_limiter_blocks_after_limit() -> None:
    current = datetime(2026, 3, 19, 12, 0, tzinfo=UTC)
    limiter = SlidingWindowRateLimiter(limit=2, window=timedelta(minutes=1), now=lambda: current)

    assert limiter.allow(1) is True
    assert limiter.allow(1) is True
    assert limiter.allow(1) is False
