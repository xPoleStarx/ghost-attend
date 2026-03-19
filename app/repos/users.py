from datetime import UTC, datetime

from sqlalchemy import select

from app.db.models import User
from app.repos.base import BaseRepository
from app.security.crypto import EncryptedValue


class UserRepository(BaseRepository):
    async def get_by_id(self, user_id: int) -> User | None:
        result = await self.session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        result = await self.session.execute(select(User).where(User.telegram_id == telegram_id))
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        telegram_id: int,
        email: EncryptedValue,
        password: EncryptedValue,
        timezone: str,
        university_url: str,
    ) -> User:
        user = User(
            telegram_id=telegram_id,
            email_encrypted=email.ciphertext,
            password_encrypted=password.ciphertext,
            key_version=email.key_version,
            timezone=timezone,
            university_url=university_url,
            created_at=datetime.now(UTC),
        )
        self.session.add(user)
        await self.session.flush()
        return user
