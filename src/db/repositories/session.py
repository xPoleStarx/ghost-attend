"""
GhostAttend — Session Repository

Agent oturum ve checkpoint CRUD işlemleri.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import AgentSession, Notification, SessionCheckpoint


class SessionRepository:
    """AgentSession tablosu üzerinde CRUD operasyonları."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, user_id: int, course_id: uuid.UUID) -> AgentSession:
        """Yeni agent session oluştur."""
        agent_session = AgentSession(
            user_id=user_id,
            course_id=course_id,
            status="pending",
        )
        self.session.add(agent_session)
        await self.session.flush()
        return agent_session

    async def get_by_id(self, session_id: uuid.UUID) -> AgentSession | None:
        """ID ile session bul."""
        result = await self.session.execute(
            select(AgentSession).where(AgentSession.id == session_id)
        )
        return result.scalar_one_or_none()

    async def update_status(
        self,
        session_id: uuid.UUID,
        status: str,
        failure_reason: str | None = None,
    ) -> None:
        """Session durumunu güncelle."""
        now = datetime.now(timezone.utc)
        values: dict = {"status": status}

        if status == "running":
            values["started_at"] = now
        elif status == "joined":
            values["joined_at"] = now
        elif status in ("completed", "failed", "cancelled"):
            values["ended_at"] = now

        if failure_reason:
            values["failure_reason"] = failure_reason

        await self.session.execute(
            update(AgentSession)
            .where(AgentSession.id == session_id)
            .values(**values)
        )

    async def increment_retry(self, session_id: uuid.UUID) -> int:
        """Retry sayısını artır, yeni değeri döndür."""
        agent_session = await self.get_by_id(session_id)
        if agent_session:
            new_count = agent_session.retry_count + 1
            await self.session.execute(
                update(AgentSession)
                .where(AgentSession.id == session_id)
                .values(retry_count=new_count)
            )
            return new_count
        return 0

    async def get_active_session(self, user_id: int) -> AgentSession | None:
        """Kullanıcının aktif (running/joined/pending) session'ını bul."""
        result = await self.session.execute(
            select(AgentSession)
            .where(
                AgentSession.user_id == user_id,
                AgentSession.status.in_(["pending", "running", "joined"]),
            )
            .order_by(AgentSession.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_recent_sessions(self, user_id: int, limit: int = 5) -> list[AgentSession]:
        """Kullanıcının son N session'ını getir."""
        result = await self.session.execute(
            select(AgentSession)
            .where(AgentSession.user_id == user_id)
            .order_by(AgentSession.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def update_metadata(self, session_id: uuid.UUID | str, metadata: dict) -> None:
        """Merge metadata into the session record."""
        agent_session = await self.get_by_id(uuid.UUID(str(session_id)))
        if agent_session is None:
            return
        merged = dict(agent_session.metadata_ or {})
        merged.update(metadata)
        await self.session.execute(
            update(AgentSession)
            .where(AgentSession.id == agent_session.id)
            .values(metadata_=merged)
        )

    async def append_metadata_event(self, session_id: uuid.UUID | str, key: str, entry: dict) -> None:
        """Append an entry to a metadata list."""
        agent_session = await self.get_by_id(uuid.UUID(str(session_id)))
        if agent_session is None:
            return
        merged = dict(agent_session.metadata_ or {})
        values = list(merged.get(key) or [])
        values.append(entry)
        merged[key] = values[-100:]
        await self.session.execute(
            update(AgentSession)
            .where(AgentSession.id == agent_session.id)
            .values(metadata_=merged)
        )

    # ── Checkpoint Methods ──

    async def add_checkpoint(
        self,
        session_id: uuid.UUID,
        checkpoint_name: str,
        screenshot_path: str | None = None,
        telegram_file_id: str | None = None,
        metadata: dict | None = None,
    ) -> SessionCheckpoint:
        """Session'a checkpoint ekle."""
        checkpoint = SessionCheckpoint(
            session_id=session_id,
            checkpoint_name=checkpoint_name,
            screenshot_path=screenshot_path,
            telegram_file_id=telegram_file_id,
            metadata_=metadata or {},
        )
        self.session.add(checkpoint)
        await self.session.flush()
        return checkpoint

    async def get_checkpoints(self, session_id: uuid.UUID) -> list[SessionCheckpoint]:
        """Session checkpoint'lerini getir."""
        result = await self.session.execute(
            select(SessionCheckpoint)
            .where(SessionCheckpoint.session_id == session_id)
            .order_by(SessionCheckpoint.occurred_at)
        )
        return list(result.scalars().all())

    # ── Notification Methods ──

    async def save_notification(
        self,
        user_id: int,
        session_id: uuid.UUID | None,
        notification_type: str,
        message: str,
    ) -> Notification:
        """Bildirim logu kaydet."""
        notification = Notification(
            user_id=user_id,
            session_id=session_id,
            type=notification_type,
            message=message,
        )
        self.session.add(notification)
        await self.session.flush()
        return notification
