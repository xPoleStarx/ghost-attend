from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta


@dataclass(slots=True)
class CommandDeduplicator:
    window: timedelta
    now: Callable[[], datetime] = lambda: datetime.now(UTC)
    _events: dict[int, deque[tuple[str, datetime]]] = field(default_factory=dict)

    def seen_recently(self, user_id: int, command_key: str) -> bool:
        current = self.now()
        bucket = self._events.setdefault(user_id, deque())
        while bucket and current - bucket[0][1] > self.window:
            bucket.popleft()
        for previous_key, _timestamp in bucket:
            if previous_key == command_key:
                return True
        bucket.append((command_key, current))
        return False
