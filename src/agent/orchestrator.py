"""
GhostAttend — Session Orchestrator

Senaryo matrisi ile AgentRunner'ı birleştiren üst düzey orkestratör.
Bir ders oturumunun tüm lifecycle'ını yönetir:
  Strateji seçimi → Cookie kontrolü → Agent çalıştırma → Senaryo handling → MFA → Retry
"""

import asyncio
import uuid
from datetime import datetime, timezone

import redis.asyncio as aioredis

from src.agent.mfa_handler import MFAHandler
from src.agent.runner import AgentRunner
from src.agent.scenarios import RecoveryAction, ScenarioHandler, ScenarioType
from src.agent.strategies.base import BaseDYSStrategy
from src.core.config import settings
from src.core.exceptions import (
    AgentJoinFailed,
    AgentLoginFailed,
    AgentLinkNotFound,
    AgentMFARequired,
    AgentPageFrozen,
    CookieExpired,
    CredentialDecryptFailed,
    CredentialNotFound,
    MeetingNotStarted,
)
from src.core.logging import get_logger

log = get_logger(__name__)


class SessionOrchestrator:
    """
    Tek bir ders için agent oturumunu orkestre eder.
    Senaryolara göre recovery, retry ve MFA yönetimi yapar.
    """

    def __init__(
        self,
        user_id: int,
        session_id: str,
        redis_client: aioredis.Redis,
        notifier=None,
        vault=None,
        session_repo=None,
    ):
        self.user_id = user_id
        self.session_id = session_id
        try:
            self.session_uuid: uuid.UUID | None = uuid.UUID(session_id)
        except Exception:
            # Testlerde veya legacy çağrılarda UUID olmayan session_id gelebilir.
            # DB güncellemeleri sadece UUID varsa yapılır.
            self.session_uuid = None
        self.redis = redis_client
        self.notifier = notifier
        self.vault = vault
        self.session_repo = session_repo
        self.scenario_handler = ScenarioHandler(notifier=notifier)

    async def attend_lesson(
        self,
        course_name: str,
        dys_url: str,
        end_time: str,
        direct_url: str | None = None,
        dys_search_hint: str | None = None,
    ) -> dict:
        """
        Bir derse katılım oturumunu baştan sona yönet.

        Akış:
        1. Cookie kontrolü (varsa cookie ile, yoksa credential ile)
        2. Agent çalıştır
        3. Hata → Senaryo tespit → Recovery action
        4. MFA → Kullanıcıdan kod al → Agent'a ilet
        5. Retry → Tekrar dene (delay ile)
        """
        log.info(
            "orchestrator.start",
            session_id=self.session_id,
            user_id=self.user_id,
            course=course_name,
        )

        # DB: session running
        if self.session_repo and self.session_uuid:
            try:
                await self.session_repo.update_status(self.session_uuid, "running")
            except Exception as e:
                log.warning("orchestrator.session_status_update_failed", error=str(e))

        # Credential'ları çöz
        username, password = None, None
        cookies = None

        if self.vault and not direct_url:
            try:
                # Önce cookie dene
                cookies = await self.vault.get_cookies(self.user_id)
            except Exception:
                cookies = None

            if not cookies:
                try:
                    username, password, _ = await self.vault.get_credentials(self.user_id)
                except CredentialNotFound as e:
                    log.error("orchestrator.credential_not_found", error=str(e))
                    if self.notifier:
                        await self.notifier.send_error(
                            user_id=self.user_id,
                            error_code="CREDENTIAL_NOT_FOUND",
                            details="Kayıtlı giriş bilgisi bulamadım.",
                        )
                    return {"status": "error", "error": "credential_not_found"}
                except CredentialDecryptFailed as e:
                    log.error("orchestrator.credential_decrypt_failed", error=str(e))
                    if self.notifier:
                        await self.notifier.send_error(
                            user_id=self.user_id,
                            error_code="CREDENTIAL_ERROR_KEY_MISMATCH",
                            details="Mevcut veriyi çözerken hata oluştu (muhtemelen anahtar değişti).",
                        )
                    return {"status": "error", "error": "credential_decrypt_failed"}
                except Exception as e:
                    log.error("orchestrator.credential_error", error=str(e))
                    if self.notifier:
                        await self.notifier.send_error(
                            user_id=self.user_id,
                            error_code="CREDENTIAL_ERROR",
                            details="❌ Giriş bilgilerin okunurken beklenmeyen bir hata oluştu.",
                        )
                    return {"status": "error", "error": "credential_error"}

        # DYS stratejisi
        strategy = BaseDYSStrategy.detect_dys(dys_url or "")

        # Agent runner
        runner = AgentRunner(
            session_id=self.session_id,
            user_id=self.user_id,
            notifier=self.notifier,
            vault=self.vault,
            redis_client=self.redis,
            session_repo=self.session_repo,
        )

        # Ana döngü — senaryo-driven
        while True:
            try:
                # Testlerde AgentRunner patch edildiğinde AsyncMock üstünde run_with_retry "varmış gibi"
                # görünebilir; bu durumda gerçek implementasyonu seçmek için type(...) kontrolü yap.
                if callable(getattr(type(runner), "run_with_retry", None)):
                    result = await runner.run_with_retry(
                        course_name=course_name,
                        dys_url=dys_url,
                        username=username,
                        password=password,
                        end_time=end_time,
                        direct_url=direct_url,
                        dys_search_hint=dys_search_hint,
                        cookies=cookies,
                    )
                else:
                    result = await runner.run(
                    course_name=course_name,
                    dys_url=dys_url,
                    username=username,
                    password=password,
                    end_time=end_time,
                    direct_url=direct_url,
                    dys_search_hint=dys_search_hint,
                    cookies=cookies,
                )

                # Başarılı
                scenario = ScenarioType.HAPPY_PATH
                await self.scenario_handler.execute_recovery(
                    scenario, self.user_id, course_name
                )

                log.info("orchestrator.completed", session_id=self.session_id)
                if self.session_repo and self.session_uuid:
                    try:
                        if result.get("status") == "cancelled":
                            await self.session_repo.update_status(self.session_uuid, "cancelled")
                        else:
                            await self.session_repo.update_status(self.session_uuid, "completed")
                    except Exception as e:
                        log.warning("orchestrator.session_status_update_failed", error=str(e))
                return result

            except AgentMFARequired as e:
                # MFA handling
                mfa_type = getattr(e, "mfa_type", "sms")
                scenario = (
                    ScenarioType.MFA_AUTHENTICATOR
                    if mfa_type == "authenticator"
                    else ScenarioType.MFA_SMS
                )

                await self.scenario_handler.execute_recovery(
                    scenario, self.user_id, course_name
                )

                # MFA kodu bekle
                mfa_handler = MFAHandler(
                    user_id=self.user_id,
                    redis_client=self.redis,
                    notifier=self.notifier,
                )
                code = await mfa_handler.request_mfa_code(mfa_type)

                if not code:
                    log.warning("orchestrator.mfa_timeout", session_id=self.session_id)
                    if self.session_repo and self.session_uuid:
                        try:
                            await self.session_repo.update_status(
                                self.session_uuid, "failed", failure_reason="mfa_timeout"
                            )
                        except Exception as e:
                            log.warning("orchestrator.session_status_update_failed", error=str(e))
                    return {"status": "mfa_timeout"}

                # MFA kodunu yeni task'a enjekte ederek yeniden dene
                # Not: Bu akış browser-use sürümüne göre "devam etme" yerine "yeniden dene" şeklinde çalışır.
                log.info("orchestrator.mfa_code_received", session_id=self.session_id)
                try:
                    if callable(getattr(type(runner), "run_with_retry", None)):
                        result = await runner.run_with_retry(
                            course_name=course_name,
                            dys_url=dys_url,
                            username=username,
                            password=password,
                            end_time=end_time,
                            direct_url=direct_url,
                            dys_search_hint=dys_search_hint,
                            cookies=cookies,
                            mfa_code=code,
                        )
                    else:
                        result = await runner.run(
                        course_name=course_name,
                        dys_url=dys_url,
                        username=username,
                        password=password,
                        end_time=end_time,
                        direct_url=direct_url,
                        dys_search_hint=dys_search_hint,
                        cookies=cookies,
                        mfa_code=code,
                    )
                    if self.session_repo and self.session_uuid:
                        try:
                            if result.get("status") == "cancelled":
                                await self.session_repo.update_status(self.session_uuid, "cancelled")
                            else:
                                await self.session_repo.update_status(self.session_uuid, "completed")
                        except Exception as e:
                            log.warning("orchestrator.session_status_update_failed", error=str(e))
                    return result
                except Exception:
                    # normal akıştaki retry/handling devam etsin
                    continue

            except CookieExpired:
                # Cookie expire → credential ile tekrar dene
                log.info("orchestrator.cookie_expired", session_id=self.session_id)
                cookies = None
                if not username and self.vault:
                    try:
                        username, password, _ = await self.vault.get_credentials(self.user_id)
                    except CredentialNotFound:
                        return {"status": "error", "error": "credential_not_found"}
                    except CredentialDecryptFailed:
                        return {"status": "error", "error": "credential_decrypt_failed"}
                    except Exception:
                        return {"status": "error", "error": "credential_error"}
                continue

            except (AgentPageFrozen, AgentJoinFailed, MeetingNotStarted) as e:
                # Retryable hatalar
                scenario = self.scenario_handler.detect_scenario("", e)
                action = await self.scenario_handler.execute_recovery(
                    scenario, self.user_id, course_name
                )

                if action == RecoveryAction.ABORT:
                    log.warning(
                        "orchestrator.max_retry",
                        session_id=self.session_id,
                        scenario=scenario.value,
                    )
                    if self.session_repo and self.session_uuid:
                        try:
                            await self.session_repo.update_status(
                                self.session_uuid, "failed", failure_reason="max_retry_exceeded"
                            )
                        except Exception as e:
                            log.warning("orchestrator.session_status_update_failed", error=str(e))
                    return {"status": "max_retry_exceeded", "scenario": scenario.value}

                config = self.scenario_handler.get_recovery(scenario)
                if config.retry_delay_seconds > 0:
                    await asyncio.sleep(config.retry_delay_seconds)
                continue

            except (AgentLoginFailed, AgentLinkNotFound) as e:
                # Non-retryable hatalar
                scenario = self.scenario_handler.detect_scenario("", e)
                await self.scenario_handler.execute_recovery(
                    scenario, self.user_id, course_name
                )
                if self.session_repo and self.session_uuid:
                    try:
                        await self.session_repo.update_status(
                            self.session_uuid, "failed", failure_reason=scenario.value
                        )
                    except Exception as e:
                        log.warning("orchestrator.session_status_update_failed", error=str(e))
                return {"status": "fatal_error", "scenario": scenario.value}

            except Exception as e:
                # Beklenmedik hata
                log.error(
                    "orchestrator.unexpected_error",
                    session_id=self.session_id,
                    error=str(e),
                )

                scenario = self.scenario_handler.detect_scenario(str(e), e)
                action = await self.scenario_handler.execute_recovery(
                    scenario, self.user_id, course_name
                )

                if action == RecoveryAction.ABORT:
                    if self.session_repo and self.session_uuid:
                        try:
                            await self.session_repo.update_status(
                                self.session_uuid, "failed", failure_reason=str(e)[:200]
                            )
                        except Exception as ex:
                            log.warning("orchestrator.session_status_update_failed", error=str(ex))
                    return {"status": "error", "error": str(e)}

                await asyncio.sleep(10)
                continue
