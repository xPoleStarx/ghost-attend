from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class MetricsCollector:
    counters: dict[str, int] = field(default_factory=dict)

    def increment(self, name: str, amount: int = 1) -> None:
        self.counters[name] = self.counters.get(name, 0) + amount

    def snapshot(self) -> dict[str, int]:
        return dict(self.counters)
