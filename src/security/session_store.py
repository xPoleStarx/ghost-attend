"""
GhostAttend — Session Cookie Store

Playwright browser context'i ile cookie persistence yönetimi.
Cookie'ler şifreli olarak DB'de saklanır, browser'a yüklenirken çözülür.
"""

from playwright.async_api import BrowserContext

from src.core.logging import get_logger
from src.security.vault import VaultService

log = get_logger(__name__)


class SessionStore:
    """Playwright cookie persistence manager."""

    def __init__(self, vault_service: VaultService):
        self.vault_service = vault_service

    async def save_browser_state(
        self,
        context: BrowserContext,
        user_id: int,
        credential_type: str = "unified",
    ) -> None:
        """
        Playwright browser context'inden cookie'leri al ve şifreli kaydet.

        Args:
            context: Aktif Playwright BrowserContext
            user_id: Telegram user_id
            credential_type: Credential tipi
        """
        storage_state = await context.storage_state()
        cookies = storage_state.get("cookies", [])

        if cookies:
            await self.vault_service.save_cookies(
                user_id=user_id,
                cookies=cookies,
                credential_type=credential_type,
            )
            log.info(
                "session_store.cookies_saved",
                user_id=user_id,
                cookie_count=len(cookies),
            )

    async def load_browser_state(
        self,
        context: BrowserContext,
        user_id: int,
        credential_type: str = "unified",
    ) -> bool:
        """
        Kayıtlı cookie'leri Playwright browser context'ine yükle.

        Args:
            context: Aktif Playwright BrowserContext
            user_id: Telegram user_id
            credential_type: Credential tipi

        Returns:
            True eğer cookie'ler başarıyla yüklendiyse, False expire olmuşsa veya yoksa.
        """
        cookies = await self.vault_service.get_cookies(
            user_id=user_id,
            credential_type=credential_type,
        )

        if not cookies:
            log.info(
                "session_store.no_cookies",
                user_id=user_id,
                reason="not_found_or_expired",
            )
            return False

        await context.add_cookies(cookies)
        log.info(
            "session_store.cookies_loaded",
            user_id=user_id,
            cookie_count=len(cookies),
        )
        return True
