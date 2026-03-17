"""
GhostAttend — Credential Repository

Credential okuma işlemleri (özellikle DYS URL gibi alanlar).
"""

from sqlalchemy import case, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Credential


class CredentialRepository:
    """Credential tablosu üzerinde read operasyonları."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_dys_url_for_user(self, user_id: int) -> str | None:
        """
        Kullanıcının DYS URL bilgisini döndür.

        Öncelik:
        - type='unified'
        - type='dys'
        """
        priority = case(
            (Credential.type == "unified", 0),
            (Credential.type == "dys", 1),
            else_=2,
        )

        result = await self.session.execute(
            select(Credential.dys_url)
            .where(
                Credential.user_id == user_id,
                Credential.type.in_(("unified", "dys")),
            )
            .order_by(priority)
            .limit(1)
        )
        return result.scalar_one_or_none()

