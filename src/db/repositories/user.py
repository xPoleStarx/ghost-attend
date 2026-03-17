"""
GhostAttend — User Repository

Kullanıcı CRUD işlemleri.
"""

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import User


class UserRepository:
    """User tablosu üzerinde CRUD operasyonları."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, user_id: int) -> User | None:
        """Telegram user_id ile kullanıcı bul."""
        result = await self.session.execute(
            select(User).where(User.id == user_id)
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        user_id: int,
        first_name: str,
        username: str | None = None,
    ) -> User:
        """Yeni kullanıcı oluştur."""
        user = User(
            id=user_id,
            first_name=first_name,
            username=username,
        )
        self.session.add(user)
        await self.session.flush()
        return user

    async def get_or_create(
        self,
        user_id: int,
        first_name: str,
        username: str | None = None,
    ) -> tuple[User, bool]:
        """Kullanıcıyı bul veya yoksa oluştur. (user, created) döndürür."""
        user = await self.get_by_id(user_id)
        if user:
            return user, False
        user = await self.create(user_id, first_name, username)
        return user, True

    async def update_onboarding_step(self, user_id: int, step: str) -> None:
        """Onboarding FSM adımını güncelle."""
        await self.session.execute(
            update(User)
            .where(User.id == user_id)
            .values(onboarding_step=step)
        )

    async def set_active(self, user_id: int, is_active: bool) -> None:
        """Kullanıcıyı aktif/pasif yap (/pause, /resume)."""
        await self.session.execute(
            update(User)
            .where(User.id == user_id)
            .values(is_active=is_active)
        )

    async def get_active_users(self) -> list[User]:
        """Tüm aktif kullanıcıları listele."""
        result = await self.session.execute(
            select(User).where(User.is_active.is_(True))
        )
        return list(result.scalars().all())
