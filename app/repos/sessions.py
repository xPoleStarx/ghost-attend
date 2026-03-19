from datetime import UTC, datetime

from sqlalchemy import select

from app.db.models import Session
from app.repos.base import BaseRepository


class SessionRepository(BaseRepository):
    async def get_by_id(self, session_id: object) -> Session | None:
        result = await self.session.execute(select(Session).where(Session.id == session_id))
        return result.scalar_one_or_none()

    async def get_active_for_user(self, user_id: int) -> Session | None:
        result = await self.session.execute(
            select(Session).where(Session.user_id == user_id, Session.is_active.is_(True))
        )
        return result.scalar_one_or_none()

    async def create(self, user_id: int, metadata: dict[str, object] | None = None) -> Session:
        session = Session(
            user_id=user_id,
            is_active=True,
            session_metadata=metadata or {},
            created_at=datetime.now(UTC),
        )
        self.session.add(session)
        await self.session.flush()
        return session

    async def close(self, session: Session) -> Session:
        session.is_active = False
        session.closed_at = datetime.now(UTC)
        await self.session.flush()
        return session

    async def list_active(self) -> list[Session]:
        result = await self.session.execute(select(Session).where(Session.is_active.is_(True)))
        return list(result.scalars().all())

    async def close_active_for_user(self, user_id: int) -> Session | None:
        session = await self.get_active_for_user(user_id)
        if session is None:
            return None
        return await self.close(session)
