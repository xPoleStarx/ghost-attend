from dataclasses import dataclass
from uuid import uuid4

import pytest

from app.scheduler.recovery import RecoveryCoordinator
from app.services.recovery import RecoveryService


@dataclass
class FakeSessionRow:
    id: object
    user_id: int
    session_metadata: dict[str, object]
    is_active: bool = True


class FakeSessionRepository:
    async def list_active(self) -> list[FakeSessionRow]:
        return [
            FakeSessionRow(id=uuid4(), user_id=11, session_metadata={"requires_login": True}),
            FakeSessionRow(id=uuid4(), user_id=12, session_metadata={"requires_login": False}),
        ]


@pytest.mark.asyncio
async def test_recovery_coordinator_lists_active_session_plans() -> None:
    coordinator = RecoveryCoordinator(
        session_repository=FakeSessionRepository(),  # type: ignore[arg-type]
        recovery_service=RecoveryService(),
    )

    plans = await coordinator.list_recovery_plans()

    assert len(plans) == 2
    assert plans[0].requires_login is True
    assert plans[1].requires_login is False
