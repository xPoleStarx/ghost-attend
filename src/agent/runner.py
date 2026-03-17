"""
GhostAttend — Agent Runner

Agent lifecycle yönetimi: browser context oluşturma, task çalıştırma,
hata yakalama, retry logic, session durumu güncelleme.
architecture.md Section 9.2
"""

import asyncio
from datetime import datetime, timezone

import redis.asyncio as aioredis

from src.agent.checkpoints import CheckpointHandler
from src.agent.mfa_handler import MFAHandler
from src.agent.task_builder import (
    build_cookie_login_task,
    build_direct_url_task,
    build_dys_to_meeting_task,
)
from src.core.config import settings
from src.core.constants import (
    AGENT_MAX_RETRY,
    AGENT_TIMEOUT_SECONDS,
    ERROR_DYS_LOGIN_FAILED,
    ERROR_JOIN_FAILED,
    ERROR_LINK_NOT_FOUND,
    ERROR_MAX_RETRY_EXCEEDED,
    ERROR_MFA_REQUIRED,
    ERROR_PAGE_FROZEN,
    REDIS_PREFIX_CANCEL,
    RETRY_DELAY_SECONDS,
)
from src.core.exceptions import (
    AgentJoinFailed,
    AgentLoginFailed,
    AgentLinkNotFound,
    AgentMaxRetryExceeded,
    AgentMFARequired,
    AgentPageFrozen,
    CookieExpired,
    MeetingNotStarted,
)
from src.core.logging import get_logger

log = get_logger(__name__)


class AgentRunner:
    """
    Web agent lifecycle manager.
    browser-use + Playwright ile ders katılımını yönetir.
    """

    def __init__(
        self,
        session_id: str,
        user_id: int,
        notifier=None,
        vault=None,
        redis_client: aioredis.Redis | None = None,
        session_repo=None,
    ):
        self.session_id = session_id
        self.user_id = user_id
        self.notifier = notifier
        self.vault = vault
        self.redis = redis_client
        self.session_repo = session_repo

    def _create_llm(self):
        """Config'e göre LLM instance oluştur."""
        provider = settings.AGENT_LLM_PROVIDER
        model = settings.AGENT_LLM_MODEL

        if provider == "google":
            from langchain_google_genai import ChatGoogleGenerativeAI

            return ChatGoogleGenerativeAI(
                model=model,
                temperature=0,
                google_api_key=settings.GOOGLE_API_KEY,
            )
        elif provider == "openai":
            from langchain_openai import ChatOpenAI

            return ChatOpenAI(
                model=model,
                temperature=0,
                api_key=settings.OPENAI_API_KEY,
            )
        elif provider == "anthropic":
            from langchain_anthropic import ChatAnthropic

            return ChatAnthropic(
                model=model,
                temperature=0,
                api_key=settings.ANTHROPIC_API_KEY,
            )
        else:
            raise ValueError(f"Desteklenmeyen LLM provider: {provider}")

    async def run(
        self,
        course_name: str,
        dys_url: str | None = None,
        username: str | None = None,
        password: str | None = None,
        end_time: str = "23:59",
        direct_url: str | None = None,
        dys_search_hint: str | None = None,
        cookies: list[dict] | None = None,
    ) -> dict:
        """
        Agent'ı çalıştır.

        Args:
            course_name: Ders adı
            dys_url: DYS adresi
            username: DYS/Teams kullanıcı adı
            password: DYS/Teams şifre
            end_time: Ders bitiş saati "HH:MM"
            direct_url: Direkt toplantı linki (varsa DYS atlanır)
            dys_search_hint: DYS'de arama ipucu
            cookies: Önceden kaydedilmiş session cookie'leri

        Returns:
            {"status": "completed", "raw": str} veya exception fırlatır
        """
        from browser_use import Agent

        log.info(
            "agent.run_start",
            session_id=self.session_id,
            user_id=self.user_id,
            course=course_name,
            has_direct_url=direct_url is not None,
            has_cookies=cookies is not None,
        )

        # Task string oluştur
        if direct_url:
            task = build_direct_url_task(course_name, direct_url, end_time)
        elif cookies:
            task = build_cookie_login_task(
                course_name, dys_url or "", end_time, dys_search_hint
            )
        else:
            task = build_dys_to_meeting_task(
                course_name,
                dys_url or "",
                username or "",
                password or "",
                end_time,
                dys_search_hint,
            )

        # Checkpoint handler
        checkpoint_handler = CheckpointHandler(
            session_id=self.session_id,
            user_id=self.user_id,
            notifier=self.notifier,
            session_repo=self.session_repo,
        )

        # MFA handler
        mfa_handler = None
        if self.redis:
            mfa_handler = MFAHandler(
                user_id=self.user_id,
                redis_client=self.redis,
                notifier=self.notifier,
            )

        # LLM oluştur
        llm = self._create_llm()

        # browser-use Agent oluştur
        agent = Agent(
            task=task,
            llm=llm,
        )

        try:
            # Timeout ile çalıştır
            timeout = settings.AGENT_TIMEOUT_SECONDS or AGENT_TIMEOUT_SECONDS

            result = await asyncio.wait_for(
                agent.run(),
                timeout=timeout,
            )

            # Sonucu parse et
            return self._parse_result(result)

        except asyncio.TimeoutError:
            raise AgentPageFrozen(f"Agent {timeout}sn içinde tamamlanamadı")

    def _parse_result(self, raw_result) -> dict:
        """Agent sonucunu parse et ve hata kodlarını exception'a çevir."""
        result_text = str(raw_result)

        error_map = {
            f"HATA_KODU: {ERROR_DYS_LOGIN_FAILED}": AgentLoginFailed("DYS giriş başarısız"),
            f"HATA_KODU: {ERROR_LINK_NOT_FOUND}": AgentLinkNotFound("Ders linki DYS'de bulunamadı"),
            f"HATA_KODU: {ERROR_MFA_REQUIRED}": AgentMFARequired("sms", "MFA doğrulaması gerekiyor"),
            f"HATA_KODU: {ERROR_JOIN_FAILED}": AgentJoinFailed("Derse katılım başarısız"),
            f"HATA_KODU: {ERROR_PAGE_FROZEN}": AgentPageFrozen("Sayfa dondu"),
            "HATA_KODU: COOKIE_EXPIRED": CookieExpired("Session cookie süresi dolmuş"),
            "HATA_KODU: MEETING_NOT_STARTED": MeetingNotStarted("Toplantı henüz başlatılmamış"),
        }

        for code, exception in error_map.items():
            if code in result_text:
                raise exception

        return {"status": "completed", "raw": result_text}

    async def run_with_retry(
        self,
        max_retry: int | None = None,
        **kwargs,
    ) -> dict:
        """
        Retry logic ile agent çalıştır.

        Args:
            max_retry: Maksimum retry sayısı (default: config'den)
            **kwargs: run() metodunun parametreleri

        Returns:
            Başarılı sonuç dict

        Raises:
            AgentMaxRetryExceeded: Tüm retry'lar başarısız olduğunda
        """
        max_retry = max_retry or settings.AGENT_MAX_RETRY or AGENT_MAX_RETRY
        last_error: Exception | None = None

        for attempt in range(1, max_retry + 1):
            try:
                log.info(
                    "agent.attempt",
                    session_id=self.session_id,
                    attempt=attempt,
                    max_retry=max_retry,
                )

                # İptal kontrolü
                if self.redis:
                    cancel_key = f"{REDIS_PREFIX_CANCEL}{self.user_id}"
                    is_cancelled = await self.redis.get(cancel_key)
                    if is_cancelled:
                        log.info("agent.cancelled_by_user", session_id=self.session_id)
                        return {"status": "cancelled"}

                result = await self.run(**kwargs)
                return result

            except AgentMFARequired:
                # MFA retry'lanmaz, kullanıcı müdahalesi gerekir
                raise

            except (AgentLoginFailed, AgentLinkNotFound) as e:
                # Bu hatalar retry'lansa da muhtemelen aynı sonucu verir
                last_error = e
                log.warning(
                    "agent.non_retryable_error",
                    session_id=self.session_id,
                    error=str(e),
                    attempt=attempt,
                )
                raise

            except (AgentPageFrozen, AgentJoinFailed, MeetingNotStarted) as e:
                last_error = e
                log.warning(
                    "agent.retryable_error",
                    session_id=self.session_id,
                    error=str(e),
                    attempt=attempt,
                )

                if attempt < max_retry:
                    # Bildirim gönder
                    if self.notifier:
                        await self.notifier.send_error(
                            user_id=self.user_id,
                            error_code="RETRY",
                            details=f"⚠️ Yeniden bağlanılıyor ({attempt}/{max_retry})...",
                        )

                    # Retry session repo güncelle
                    if self.session_repo:
                        await self.session_repo.increment_retry(self.session_id)

                    await asyncio.sleep(RETRY_DELAY_SECONDS)
                else:
                    break

            except Exception as e:
                last_error = e
                log.error(
                    "agent.unexpected_error",
                    session_id=self.session_id,
                    error=str(e),
                    attempt=attempt,
                )
                if attempt < max_retry:
                    await asyncio.sleep(RETRY_DELAY_SECONDS)
                else:
                    break

        # Tüm retry'lar başarısız
        raise AgentMaxRetryExceeded(
            retry_count=max_retry,
            message=f"Tüm denemeler başarısız: {last_error}",
        )
