from app.domain.schemas import RecoveryTaskPlan
from app.repos.sessions import SessionRepository
from app.services.recovery import RecoveryService


class RecoveryCoordinator:
    def __init__(self, session_repository: SessionRepository, recovery_service: RecoveryService) -> None:
        self.session_repository = session_repository
        self.recovery_service = recovery_service

    async def list_recovery_plans(self) -> list[RecoveryTaskPlan]:
        sessions = await self.session_repository.list_active()
        return [
            self.recovery_service.build_recovery_plan(
                user_id=session.user_id,
                session_id=str(session.id),
                session_metadata=session.session_metadata,
            )
            for session in sessions
        ]
