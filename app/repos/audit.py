from datetime import UTC, datetime

from app.db.models import AuditEventModel
from app.domain.schemas import AuditEvent
from app.repos.base import BaseRepository


class AuditRepository(BaseRepository):
    async def record(self, event: AuditEvent) -> AuditEventModel:
        row = AuditEventModel(
            user_id=event.user_id,
            session_id=event.session_id,
            event_type=event.event_type,
            payload_json=event.payload,
            created_at=datetime.now(UTC),
        )
        self.session.add(row)
        await self.session.flush()
        return row
