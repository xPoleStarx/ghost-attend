from __future__ import annotations

from dataclasses import dataclass

from app.domain.schemas import AuditEvent
from app.repos.audit import AuditRepository
from app.services.metrics import MetricsCollector


@dataclass(slots=True)
class ObservabilityService:
    audit_repository: AuditRepository | None
    metrics: MetricsCollector

    async def record_event(self, event: AuditEvent) -> None:
        self.metrics.increment(f"audit.{event.event_type}")
        if self.audit_repository is not None:
            await self.audit_repository.record(event)

    def increment(self, metric_name: str, amount: int = 1) -> None:
        self.metrics.increment(metric_name, amount)
