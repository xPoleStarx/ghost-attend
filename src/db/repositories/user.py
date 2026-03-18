"""
GhostAttend - User Repository

Kullanici CRUD islemleri.
"""

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import User


class UserRepository:
    """User tablosu uzerinde CRUD operasyonlari."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, user_id: int) -> User | None:
        """Telegram user_id ile kullanici bul."""
        result = await self.session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def create(
        self,
        user_id: int,
        first_name: str,
        username: str | None = None,
        timezone: str | None = None,
    ) -> User:
        """Yeni kullanici olustur."""
        user = User(
            id=user_id,
            first_name=first_name,
            username=username,
            timezone=timezone or "Europe/Istanbul",
        )
        self.session.add(user)
        await self.session.flush()
        return user

    async def get_or_create(
        self,
        user_id: int,
        first_name: str,
        username: str | None = None,
        timezone: str | None = None,
    ) -> tuple[User, bool]:
        """Kullaniciyi bul veya yoksa olustur. (user, created) dondurur."""
        user = await self.get_by_id(user_id)
        if user:
            return user, False
        user = await self.create(user_id, first_name, username, timezone=timezone)
        return user, True

    async def create_or_update(
        self,
        user_id: int,
        first_name: str,
        username: str | None = None,
        timezone: str | None = None,
    ) -> User:
        """Kullaniciyi bulup guncelle, yoksa olustur."""
        user = await self.get_by_id(user_id)
        if user:
            user.first_name = first_name
            user.username = username
            if timezone:
                user.timezone = timezone
            return user
        return await self.create(user_id, first_name, username, timezone=timezone)

    async def update_onboarding_step(self, user_id: int, step: str) -> None:
        """Onboarding FSM adimini guncelle."""
        await self.session.execute(
            update(User).where(User.id == user_id).values(onboarding_step=step)
        )

    async def update_timezone(self, user_id: int, timezone_name: str) -> None:
        """Kullanici timezone bilgisini guncelle."""
        await self.session.execute(
            update(User).where(User.id == user_id).values(timezone=timezone_name)
        )

    async def get_timezone(self, user_id: int) -> str | None:
        """Kullanicinin timezone bilgisini getir."""
        result = await self.session.execute(
            select(User.timezone).where(User.id == user_id)
        )
        return result.scalar_one_or_none()

    async def set_active(self, user_id: int, is_active: bool) -> None:
        """Kullaniciyi aktif/pasif yap."""
        await self.session.execute(
            update(User).where(User.id == user_id).values(is_active=is_active)
        )

    async def get_active_users(self) -> list[User]:
        """Tum aktif kullanicilari listele."""
        result = await self.session.execute(select(User).where(User.is_active.is_(True)))
        return list(result.scalars().all())

    async def delete_user_and_related(self, user_id: int) -> None:
        """
        Kullaniciyi ve ona bagli tum verileri sil.

        Not:
        - credentials ve courses zaten User.relationship uzerinde
          cascade="all, delete-orphan" + ondelete="CASCADE" ile tanimli.
        - agent_sessions ve notifications icin once bu tablolardan silip,
          ardindan User kaydini siliyoruz.
        """
        from src.db.models import AgentSession, Notification

        await self.session.execute(
            delete(Notification).where(Notification.user_id == user_id)
        )
        await self.session.execute(
            delete(AgentSession).where(AgentSession.user_id == user_id)
        )
        await self.session.execute(delete(User).where(User.id == user_id))
