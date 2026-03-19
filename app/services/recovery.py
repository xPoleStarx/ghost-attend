from app.domain.schemas import RecoveryTaskPlan


class RecoveryService:
    def build_recovery_plan(
        self,
        *,
        user_id: int,
        session_id: str,
        session_metadata: dict[str, object] | None = None,
    ) -> RecoveryTaskPlan:
        metadata = session_metadata or {}
        requires_login = bool(metadata.get("requires_login", True))
        return RecoveryTaskPlan(
            user_id=user_id,
            session_id=session_id,
            requires_login=requires_login,
        )
