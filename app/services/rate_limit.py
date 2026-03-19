from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta


@dataclass(slots=True)
class SlidingWindowRateLimiter:
    limit: int
    window: timedelta
    now: Callable[[], datetime] = lambda: datetime.now(UTC)
    _events: dict[int, deque[datetime]] = field(default_factory=dict)

    def allow(self, user_id: int) -> bool:
        current = self.now()
        bucket = self._events.setdefault(user_id, deque())
        while bucket and current - bucket[0] > self.window:
            bucket.popleft()
        if len(bucket) >= self.limit:
            return False
        bucket.append(current)
        return True
