"""
GhostAttend — MFA Handler

MFA/2FA interrupt akışını yönetir.
Agent MFA tespit ettiğinde durur → Redis'e bildirim yazar →
Telegram üzerinden kullanıcıdan kod alır → Redis'ten okur → devam eder.
architecture.md Section 10.4, 10.5
"""

import asyncio

import redis.asyncio as aioredis

from src.core.constants import (
    MFA_PUSH_TIMEOUT_SECONDS,
    MFA_SMS_TIMEOUT_SECONDS,
    REDIS_PREFIX_MFA,
)
from src.core.logging import get_logger

log = get_logger(__name__)


class MFAHandler:
    """
    MFA interrupt yöneticisi.
    Redis pub/sub ile Telegram bot handler arasında köprü kurar.

    Akış:
    1. Agent MFA tespit eder → request_mfa_code() çağırır
    2. Telegram'a bildirim gönderir
    3. Redis'te MFA kodunu bekler
    4. Kullanıcı Telegram'dan kodu yazar → Bot Redis'e yazar
    5. Agent kodu okur → Forma girer → Devam eder
    """

    def __init__(
        self,
        user_id: int,
        redis_client: aioredis.Redis,
        notifier=None,
    ):
        self.user_id = user_id
        self.redis = redis_client
        self.notifier = notifier

    def _mfa_key(self) -> str:
        """Kullanıcıya özel Redis MFA key."""
        return f"{REDIS_PREFIX_MFA}{self.user_id}"

    async def request_mfa_code(self, mfa_type: str = "sms") -> str | None:
        """
        Kullanıcıdan MFA kodu iste ve bekle.

        Args:
            mfa_type: 'sms' | 'authenticator' | 'email'

        Returns:
            MFA kodu string veya timeout ise None
        """
        timeout = (
            MFA_PUSH_TIMEOUT_SECONDS
            if mfa_type == "authenticator"
            else MFA_SMS_TIMEOUT_SECONDS
        )

        log.info(
            "mfa.requesting",
            user_id=self.user_id,
            mfa_type=mfa_type,
            timeout=timeout,
        )

        # Önceki kodu temizle
        await self.redis.delete(self._mfa_key())

        # Telegram üzerinden bildirim gönder
        if self.notifier:
            if mfa_type == "authenticator":
                await self.notifier.send_error(
                    user_id=self.user_id,
                    error_code="MFA_AUTHENTICATOR",
                    details=(
                        f"📱 Telefonundaki Microsoft Authenticator'dan onay ver.\n"
                        f"Onayladıktan sonra /confirmed yaz.\n"
                        f"⏰ {timeout} saniye süren var."
                    ),
                )
            else:
                await self.notifier.send_error(
                    user_id=self.user_id,
                    error_code="MFA_REQUIRED",
                    details=f"⏰ {timeout} saniye içinde kodu buraya yaz.",
                )

        # Redis'te kodu bekle (polling)
        code = await self._wait_for_code(timeout)

        if code:
            log.info("mfa.code_received", user_id=self.user_id, mfa_type=mfa_type)
        else:
            log.warning("mfa.timeout", user_id=self.user_id, mfa_type=mfa_type)
            if self.notifier:
                await self.notifier.send_error(
                    user_id=self.user_id,
                    error_code="MFA_TIMEOUT",
                    details="⏰ MFA zaman aşımı. Oturum iptal ediliyor.",
                )

        return code

    async def _wait_for_code(self, timeout: int) -> str | None:
        """Redis'te MFA kodunu bekle (polling)."""
        elapsed = 0
        poll_interval = 2  # Her 2 saniyede bir kontrol

        while elapsed < timeout:
            code = await self.redis.get(self._mfa_key())
            if code:
                # Kodu temizle (tek kullanımlık)
                await self.redis.delete(self._mfa_key())
                return code.decode() if isinstance(code, bytes) else str(code)

            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

        return None

    async def submit_code(self, code: str) -> None:
        """
        Telegram bot handler'dan çağrılır.
        Kullanıcının girdiği MFA kodunu Redis'e yazar.
        """
        await self.redis.set(
            self._mfa_key(),
            code,
            ex=300,  # 5 dakika TTL
        )
        log.info("mfa.code_submitted", user_id=self.user_id)

    async def submit_confirmation(self) -> None:
        """
        Authenticator push onayı için /confirmed komutu.
        Redis'e 'CONFIRMED' yazar.
        """
        await self.redis.set(
            self._mfa_key(),
            "CONFIRMED",
            ex=300,
        )
        log.info("mfa.push_confirmed", user_id=self.user_id)

    async def is_cancelled(self, cancel_key: str) -> bool:
        """Agent'ın iptal edilip edilmediğini kontrol et."""
        result = await self.redis.get(cancel_key)
        return result is not None
