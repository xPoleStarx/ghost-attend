"""GhostAttend - Agent Runner."""

from __future__ import annotations

import asyncio
import os
import time

import redis.asyncio as aioredis
from playwright.async_api import async_playwright

from src.agent.checkpoints import CheckpointHandler
from src.agent.llm import call_llm
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
    CHECKPOINT_JOINED,
    ERROR_DYS_LOGIN_FAILED,
    ERROR_JOIN_FAILED,
    ERROR_LINK_NOT_FOUND,
    ERROR_MFA_REQUIRED,
    ERROR_PAGE_FROZEN,
    REDIS_PREFIX_CANCEL,
    RETRY_DELAY_SECONDS,
)
from src.core.exceptions import (
    AgentBrowserEnvironmentError,
    AgentCancelled,
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
from src.runtime import BrowserControlService, BrowserSession, RuntimeEngine, RuntimeIPC
from src.runtime.models import RuntimeGoal
from src.runtime.planner import RuntimePlanner

log = get_logger(__name__)


def _should_use_headless_browser() -> bool:
    """Force headless mode in environments without a display server."""
    return bool(getattr(settings, "BROWSER_HEADLESS", True)) or not bool(os.environ.get("DISPLAY"))


def _is_display_environment_error(exc: Exception) -> bool:
    message = str(exc or "").casefold()
    return any(
        marker in message
        for marker in (
            "missing x server",
            "$display",
            "headed browser without having a xserver",
            "platform failed to initialize",
        )
    )


def _raise_if_display_environment_error(exc: Exception) -> None:
    if _is_display_environment_error(exc):
        raise AgentBrowserEnvironmentError(
            "Tarayici baslatilamadi; sunucuda grafik oturumu yok, headless mod gerekiyor."
        ) from exc


class AgentRunner:
    """Web agent lifecycle manager."""

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
        """Create the legacy browser-use LLM client."""
        provider = settings.AGENT_LLM_PROVIDER
        model = settings.AGENT_LLM_MODEL

        if provider == "google":
            from langchain_google_genai import ChatGoogleGenerativeAI

            return ChatGoogleGenerativeAI(
                model=model,
                temperature=0,
                google_api_key=settings.GOOGLE_API_KEY,
            )
        if provider == "openai":
            from langchain_openai import ChatOpenAI

            return ChatOpenAI(
                model=model,
                temperature=0,
                api_key=settings.OPENAI_API_KEY,
            )
        if provider == "anthropic":
            from langchain_anthropic import ChatAnthropic

            return ChatAnthropic(
                model=model,
                temperature=0,
                api_key=settings.ANTHROPIC_API_KEY,
            )
        raise ValueError(f"Unsupported LLM provider: {provider}")

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
        mfa_code: str | None = None,
    ) -> dict:
        """Run the session using the custom runtime first, then legacy fallback."""
        log.info(
            "agent.run_start",
            session_id=self.session_id,
            user_id=self.user_id,
            course=course_name,
            has_direct_url=direct_url is not None,
            has_cookies=cookies is not None,
        )

        if settings.AGENT_RUNTIME_MODE == "custom":
            try:
                return await self._run_custom_runtime(
                    course_name=course_name,
                    dys_url=dys_url,
                    username=username,
                    password=password,
                    end_time=end_time,
                    direct_url=direct_url,
                    dys_search_hint=dys_search_hint,
                    cookies=cookies,
                    mfa_code=mfa_code,
                )
            except Exception:
                if not settings.AGENT_ENABLE_LEGACY_FALLBACK:
                    raise
                log.warning(
                    "agent.custom_runtime_failed_falling_back",
                    session_id=self.session_id,
                    user_id=self.user_id,
                    exc_info=True,
                )

        return await self._run_legacy(
            course_name=course_name,
            dys_url=dys_url,
            username=username,
            password=password,
            end_time=end_time,
            direct_url=direct_url,
            dys_search_hint=dys_search_hint,
            cookies=cookies,
            mfa_code=mfa_code,
        )

    async def _run_custom_runtime(
        self,
        *,
        course_name: str,
        dys_url: str | None,
        username: str | None,
        password: str | None,
        end_time: str,
        direct_url: str | None,
        dys_search_hint: str | None,
        cookies: list[dict] | None,
        mfa_code: str | None,
    ) -> dict:
        headless = _should_use_headless_browser()
        browser_service = BrowserControlService()
        planner = RuntimePlanner(call_llm)
        runtime_ipc = RuntimeIPC(self.redis) if self.redis else None
        runtime = RuntimeEngine(
            session_id=self.session_id,
            user_id=self.user_id,
            browser_service=browser_service,
            planner=planner,
            notifier=self.notifier,
            session_repo=self.session_repo,
            runtime_ipc=runtime_ipc,
        )

        target_url = direct_url or dys_url
        if not target_url:
            raise AgentJoinFailed("Dys URL or direct URL is required.")

        async with async_playwright() as playwright:
            try:
                browser = await playwright.chromium.launch(headless=headless)
            except Exception as exc:
                _raise_if_display_environment_error(exc)
                raise
            context = await browser.new_context()
            if cookies:
                try:
                    await context.add_cookies(cookies)
                except Exception:
                    log.warning("agent.custom_runtime_cookie_load_failed", session_id=self.session_id, exc_info=True)
            page = await context.new_page()
            await page.goto(target_url)

            browser_session = BrowserSession(
                session_id=self.session_id,
                page=page,
                context=context,
                browser=browser,
            )
            await runtime.attach(browser_session)

            if self.session_repo:
                await self.session_repo.update_metadata(
                    self.session_id,
                    {
                        "runtime_mode": "custom",
                        "runtime_goal": {
                            "course_name": course_name,
                            "target_url": target_url,
                            "dys_search_hint": dys_search_hint,
                            "has_credentials": bool(username and password),
                            "has_mfa_code": bool(mfa_code),
                        },
                    },
                )

            try:
                result = await runtime.run_goal(
                    RuntimeGoal(
                        mode="join_lesson",
                        instruction=(
                            f"Join the {course_name} lesson safely. "
                            f"Search for {dys_search_hint or course_name} if the page is a DYS dashboard. "
                            f"Keep microphone and camera off. Stay until {end_time}."
                        ),
                        course_name=course_name,
                        end_time=end_time,
                        metadata={
                            "dys_url": dys_url,
                            "direct_url": direct_url,
                            "username": username or "",
                            "password": password or "",
                            "mfa_code": mfa_code or "",
                        },
                    )
                )
            finally:
                if self.session_repo:
                    latest_snapshot = runtime.state_store.latest_snapshot
                    await self.session_repo.update_metadata(
                        self.session_id,
                        {
                            "runtime_last_snapshot": latest_snapshot.model_dump(mode="json") if latest_snapshot else None,
                            "runtime_decision_log": runtime.state_store.decision_log[-20:],
                        },
                    )
                await runtime.detach()
                await context.close()
                await browser.close()

        return result

    async def _run_legacy(
        self,
        *,
        course_name: str,
        dys_url: str | None,
        username: str | None,
        password: str | None,
        end_time: str,
        direct_url: str | None,
        dys_search_hint: str | None,
        cookies: list[dict] | None,
        mfa_code: str | None,
    ) -> dict:
        from browser_use import Agent

        if direct_url:
            task = build_direct_url_task(course_name, direct_url, end_time, mfa_code=mfa_code)
        elif cookies:
            task = build_cookie_login_task(
                course_name, dys_url or "", end_time, dys_search_hint, mfa_code=mfa_code
            )
        else:
            task = build_dys_to_meeting_task(
                course_name,
                dys_url or "",
                username or "",
                password or "",
                end_time,
                dys_search_hint,
                mfa_code=mfa_code,
            )

        checkpoint_handler = CheckpointHandler(
            session_id=self.session_id,
            user_id=self.user_id,
            notifier=self.notifier,
            session_repo=self.session_repo,
        )

        last_live_report_at = 0.0
        live_report_interval_s = 180

        if self.redis:
            MFAHandler(
                user_id=self.user_id,
                redis_client=self.redis,
                notifier=self.notifier,
            )

        llm = self._create_llm()

        async def _on_step(step_info: dict) -> None:
            if self.redis:
                cancel_key = f"{REDIS_PREFIX_CANCEL}{self.user_id}"
                if await self.redis.get(cancel_key):
                    raise AgentCancelled("User cancelled")
            await checkpoint_handler.handle_step(step_info)

            nonlocal last_live_report_at
            now = time.monotonic()
            if (
                CHECKPOINT_JOINED in checkpoint_handler.detected_checkpoints
                and (now - last_live_report_at) >= live_report_interval_s
            ):
                screenshot_bytes = step_info.get("screenshot")
                if screenshot_bytes:
                    try:
                        await checkpoint_handler.send_manual_screenshot(
                            screenshot_bytes=screenshot_bytes,
                            caption="Su anda dersteyim. Kisa durum raporu.",
                        )
                        last_live_report_at = now
                    except Exception:
                        pass

        headless = _should_use_headless_browser()
        agent = None
        init_errors: list[str] = []
        on_step_supported = False

        candidate_kwargs = [
            {"task": task, "llm": llm, "on_step": _on_step, "browser_config": {"headless": headless}},
            {"task": task, "llm": llm, "on_step": _on_step, "headless": headless},
            {"task": task, "llm": llm, "browser_config": {"headless": headless}},
            {"task": task, "llm": llm, "headless": headless},
        ]

        for kwargs in candidate_kwargs:
            try:
                agent = Agent(**kwargs)
                on_step_supported = "on_step" in kwargs
                break
            except TypeError as exc:
                init_errors.append(str(exc))
                continue

        if agent is None:
            log.error(
                "agent.init_failed",
                session_id=self.session_id,
                user_id=self.user_id,
                headless=headless,
                errors=init_errors[-3:],
            )
            raise AgentJoinFailed("Browser or legacy agent could not be started.")

        if not on_step_supported:
            log.warning("agent.on_step_not_supported", session_id=self.session_id)

        try:
            timeout = settings.AGENT_TIMEOUT_SECONDS or AGENT_TIMEOUT_SECONDS
            result = await asyncio.wait_for(agent.run(), timeout=timeout)
            if self.session_repo:
                await self.session_repo.update_metadata(self.session_id, {"runtime_mode": "legacy"})
            return self._parse_result(result)
        except asyncio.TimeoutError as exc:
            raise AgentPageFrozen(f"Agent timed out after {timeout} seconds") from exc
        except AgentCancelled:
            return {"status": "cancelled"}
        except Exception as exc:
            _raise_if_display_environment_error(exc)
            raise

    def _parse_result(self, raw_result) -> dict:
        """Parse the legacy agent result."""

        def _has_empty_history(obj, depth: int = 0) -> bool:
            if depth > 4:
                return False
            try:
                all_results = getattr(obj, "all_results")
            except Exception:
                all_results = None
            if all_results is not None:
                try:
                    return len(all_results) == 0
                except Exception:
                    return not all_results
            if isinstance(obj, dict):
                return any(_has_empty_history(value, depth + 1) for value in obj.values())
            if isinstance(obj, (list, tuple, set)):
                return any(_has_empty_history(value, depth + 1) for value in obj)
            return False

        result_text = str(raw_result)
        if _is_display_environment_error(Exception(result_text)):
            raise AgentBrowserEnvironmentError(
                "Tarayici baslatilamadi; sunucuda grafik oturumu yok, headless mod gerekiyor."
            )
        if _has_empty_history(raw_result) or "AgentHistoryList(all_results=[]" in result_text:
            raise AgentJoinFailed("Browser failed to initialize or no actions were executed.")

        error_map = {
            f"HATA_KODU: {ERROR_DYS_LOGIN_FAILED}": AgentLoginFailed("DYS login failed"),
            f"HATA_KODU: {ERROR_LINK_NOT_FOUND}": AgentLinkNotFound("Meeting link not found"),
            f"HATA_KODU: {ERROR_MFA_REQUIRED}": AgentMFARequired("sms", "MFA required"),
            f"HATA_KODU: {ERROR_JOIN_FAILED}": AgentJoinFailed("Failed to join the lesson"),
            f"HATA_KODU: {ERROR_PAGE_FROZEN}": AgentPageFrozen("Page frozen"),
            "HATA_KODU: COOKIE_EXPIRED": CookieExpired("Saved session cookie expired"),
            "HATA_KODU: MEETING_NOT_STARTED": MeetingNotStarted("Meeting has not started yet"),
        }
        for code, exception in error_map.items():
            if code in result_text:
                raise exception
        return {"status": "completed", "raw": result_text}

    async def run_with_retry(self, max_retry: int | None = None, **kwargs) -> dict:
        """Run the agent with retry logic."""
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
                if self.redis:
                    cancel_key = f"{REDIS_PREFIX_CANCEL}{self.user_id}"
                    if await self.redis.get(cancel_key):
                        log.info("agent.cancelled_by_user", session_id=self.session_id)
                        return {"status": "cancelled"}
                return await self.run(**kwargs)
            except AgentMFARequired:
                raise
            except AgentBrowserEnvironmentError:
                raise
            except AgentCancelled:
                log.info("agent.cancelled_by_user", session_id=self.session_id)
                return {"status": "cancelled"}
            except (AgentLoginFailed, AgentLinkNotFound) as exc:
                last_error = exc
                log.warning("agent.non_retryable_error", session_id=self.session_id, error=str(exc), attempt=attempt)
                raise
            except (AgentPageFrozen, AgentJoinFailed, MeetingNotStarted) as exc:
                last_error = exc
                log.warning("agent.retryable_error", session_id=self.session_id, error=str(exc), attempt=attempt)
                if attempt < max_retry:
                    if self.notifier:
                        await self.notifier.send_error(
                            user_id=self.user_id,
                            error_code="RETRY",
                            details=f"Yeniden baglaniliyor ({attempt}/{max_retry})...",
                        )
                    if self.session_repo:
                        await self.session_repo.increment_retry(self.session_id)
                    await asyncio.sleep(RETRY_DELAY_SECONDS)
                else:
                    break
            except Exception as exc:
                last_error = exc
                log.error("agent.unexpected_error", session_id=self.session_id, error=str(exc), attempt=attempt)
                if attempt < max_retry:
                    await asyncio.sleep(RETRY_DELAY_SECONDS)
                else:
                    break

        raise AgentMaxRetryExceeded(
            retry_count=max_retry,
            message=f"All attempts failed: {last_error}",
        )
