import pytest

from app.domain.schemas import AuditEvent
from app.services.metrics import MetricsCollector
from app.services.observability import ObservabilityService


class FakeAuditRepository:
    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    async def record(self, event: AuditEvent) -> AuditEvent:
        self.events.append(event)
        return event


@pytest.mark.asyncio
async def test_observability_records_metric_and_audit_event() -> None:
    repo = FakeAuditRepository()
    metrics = MetricsCollector()
    service = ObservabilityService(audit_repository=repo, metrics=metrics)  # type: ignore[arg-type]

    await service.record_event(AuditEvent(user_id=7, event_type="meeting_joined"))

    assert metrics.snapshot()["audit.meeting_joined"] == 1
    assert len(repo.events) == 1
