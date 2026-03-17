"""
GhostAttend — Credential Vault Service

Credential CRUD işlemleri — şifreleme ile entegre.
Encryption modülünü ve DB'yi birleştirerek credential yaşam döngüsünü yönetir.
"""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import COOKIE_EXPIRY_DAYS
from src.core.exceptions import CredentialNotFound
from src.db.models import Credential
from src.security.encryption import CredentialVault


class VaultService:
    """Credential CRUD — şifreleme + DB birleşimi."""

    def __init__(self, session: AsyncSession, vault: CredentialVault):
        self.session = session
        self.vault = vault

    async def save_credentials(
        self,
        user_id: int,
        email: str,
        password: str,
        credential_type: str = "unified",
        dys_url: str | None = None,
    ) -> Credential:
        """
        Kullanıcı credential'ını şifreli olarak kaydet.
        Aynı tipteki mevcut credential varsa güncelle.
        """
        # Mevcut credential var mı kontrol et
        result = await self.session.execute(
            select(Credential).where(
                Credential.user_id == user_id,
                Credential.type == credential_type,
            )
        )
        existing = result.scalar_one_or_none()

        email_enc = self.vault.encrypt(user_id, email)
        password_enc = self.vault.encrypt(user_id, password)

        if existing:
            # Güncelle
            await self.session.execute(
                update(Credential)
                .where(Credential.id == existing.id)
                .values(
                    email_enc=email_enc,
                    password_enc=password_enc,
                    dys_url=dys_url or existing.dys_url,
                    last_verified=None,  # Yeniden doğrulanmalı
                )
            )
            return existing
        else:
            # Yeni oluştur
            credential = Credential(
                user_id=user_id,
                type=credential_type,
                dys_url=dys_url,
                email_enc=email_enc,
                password_enc=password_enc,
            )
            self.session.add(credential)
            await self.session.flush()
            return credential

    async def get_credentials(
        self, user_id: int, credential_type: str = "unified"
    ) -> tuple[str, str, str | None]:
        """
        Kullanıcı credential'ını çöz ve döndür.

        Returns:
            (email, password, dys_url)

        Raises:
            CredentialNotFound: Credential bulunamadı
        """
        result = await self.session.execute(
            select(Credential).where(
                Credential.user_id == user_id,
                Credential.type == credential_type,
            )
        )
        cred = result.scalar_one_or_none()

        if not cred:
            raise CredentialNotFound(
                f"Credential bulunamadı: user_id={user_id}, type={credential_type}"
            )

        email = self.vault.decrypt(user_id, cred.email_enc)
        password = self.vault.decrypt(user_id, cred.password_enc)

        return email, password, cred.dys_url

    async def mark_verified(self, user_id: int, credential_type: str = "unified") -> None:
        """Credential'ın doğrulandığını işaretle."""
        await self.session.execute(
            update(Credential)
            .where(
                Credential.user_id == user_id,
                Credential.type == credential_type,
            )
            .values(last_verified=datetime.now(timezone.utc))
        )

    async def save_cookies(
        self, user_id: int, cookies: list[dict], credential_type: str = "unified"
    ) -> None:
        """Session cookie'leri şifreli olarak kaydet."""
        cookie_enc = self.vault.encrypt_cookies(user_id, cookies)
        expires_at = datetime.now(timezone.utc) + timedelta(days=COOKIE_EXPIRY_DAYS)

        await self.session.execute(
            update(Credential)
            .where(
                Credential.user_id == user_id,
                Credential.type == credential_type,
            )
            .values(
                cookie_enc=cookie_enc,
                cookie_expires_at=expires_at,
            )
        )

    async def get_cookies(self, user_id: int, credential_type: str = "unified") -> list[dict] | None:
        """Session cookie'leri çöz ve döndür. Expire olmuşsa None döndür."""
        result = await self.session.execute(
            select(Credential).where(
                Credential.user_id == user_id,
                Credential.type == credential_type,
            )
        )
        cred = result.scalar_one_or_none()

        if not cred or not cred.cookie_enc:
            return None

        # Expire kontrolü
        if cred.cookie_expires_at and cred.cookie_expires_at < datetime.now(timezone.utc):
            return None

        return self.vault.decrypt_cookies(user_id, cred.cookie_enc)

    async def get_expiring_credentials(self, days_ahead: int = 7) -> list[Credential]:
        """Expire olacak cookie'leri bul (günlük kontrol için)."""
        threshold = datetime.now(timezone.utc) + timedelta(days=days_ahead)
        result = await self.session.execute(
            select(Credential).where(
                Credential.cookie_expires_at.isnot(None),
                Credential.cookie_expires_at < threshold,
                Credential.cookie_expires_at > datetime.now(timezone.utc),
            )
        )
        return list(result.scalars().all())
