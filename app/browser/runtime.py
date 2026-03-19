from __future__ import annotations

from datetime import UTC, datetime
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.domain.enums import MeetingState

try:
    from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright
except Exception:  # noqa: BLE001
    Browser = Any  # type: ignore[assignment,misc]
    BrowserContext = Any  # type: ignore[assignment,misc]
    Page = Any  # type: ignore[assignment,misc]
    Playwright = Any  # type: ignore[assignment,misc]
    async_playwright = None  # type: ignore[assignment]


@dataclass(slots=True)
class BrowserSessionHandle:
    user_id: int
    session_id: str
    meeting_state: MeetingState = MeetingState.IDLE
    is_logged_in: bool = False
    university_url: str | None = None
    active_course_id: int | None = None
    active_course_name: str | None = None
    waiting_room_since: datetime | None = None
    last_error: str | None = None
    last_screenshot_path: str | None = None
    browser_context: BrowserContext | None = None
    page: Page | None = None
    events: list[str] = field(default_factory=list)


@dataclass(slots=True)
class BrowserRuntime:
    headless: bool
    screenshot_dir: Path
    executable_path: Path | None = None
    is_started: bool = False
    playwright: Playwright | None = None
    browser: Browser | None = None

    async def start(self) -> None:
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        if not self.is_started and async_playwright is not None:
            self.playwright = await async_playwright().start()
            launch_kwargs: dict[str, Any] = {"headless": self.headless}
            if self.executable_path is not None:
                launch_kwargs["executable_path"] = str(self.executable_path)
            self.browser = await self.playwright.chromium.launch(**launch_kwargs)
        self.is_started = True

    async def stop(self) -> None:
        if self.browser is not None:
            await self.browser.close()
            self.browser = None
        if self.playwright is not None:
            await self.playwright.stop()
            self.playwright = None
        self.is_started = False

    async def create_context(self) -> BrowserContext | None:
        await self.start()
        if self.browser is None:
            return None
        return await self.browser.new_context(
            permissions=["microphone", "camera"],
            ignore_https_errors=True,
        )

    async def ensure_page(self, handle: BrowserSessionHandle) -> Page | None:
        if handle.page is not None:
            return handle.page
        if handle.browser_context is None:
            handle.browser_context = await self.create_context()
        if handle.browser_context is None:
            return None
        handle.page = await handle.browser_context.new_page()
        return handle.page

    async def goto(self, handle: BrowserSessionHandle, url: str, timeout_ms: int) -> bool:
        page = await self.ensure_page(handle)
        if page is None:
            return False
        await page.goto(url, wait_until="networkidle", timeout=timeout_ms)
        return True

    async def capture_screenshot(self, handle: BrowserSessionHandle, name: str) -> str:
        await self.start()
        filename = f"{handle.user_id}_{handle.session_id}_{name}.png"
        screenshot_path = self.screenshot_dir / filename
        page = await self.ensure_page(handle)
        if page is not None:
            try:
                await page.wait_for_load_state("networkidle", timeout=5000)
            except Exception:  # noqa: BLE001
                pass
            await page.screenshot(path=str(screenshot_path), full_page=True)
        else:
            screenshot_path.write_bytes(b"placeholder")
        handle.last_screenshot_path = str(screenshot_path)
        return str(screenshot_path)


@dataclass(slots=True)
class BrowserContextManager:
    runtime: BrowserRuntime
    _contexts: dict[int, BrowserSessionHandle] = field(default_factory=dict)

    async def get_or_create_context(self, user_id: int, session_id: str) -> BrowserSessionHandle:
        await self.runtime.start()
        handle = self._contexts.get(user_id)
        if handle is None:
            handle = BrowserSessionHandle(user_id=user_id, session_id=session_id)
            self._contexts[user_id] = handle
        return handle

    async def get_context(self, user_id: int) -> BrowserSessionHandle | None:
        return self._contexts.get(user_id)

    async def list_contexts(self) -> list[BrowserSessionHandle]:
        return list(self._contexts.values())

    async def destroy_context(self, user_id: int) -> None:
        handle = self._contexts.pop(user_id, None)
        if handle is None:
            return
        if handle.page is not None:
            await handle.page.close()
        if handle.browser_context is not None:
            await handle.browser_context.close()

    async def mark_logged_in(self, user_id: int, university_url: str) -> BrowserSessionHandle | None:
        handle = await self.get_context(user_id)
        if handle is None:
            return None
        handle.is_logged_in = True
        handle.university_url = university_url
        handle.meeting_state = MeetingState.PREPARING
        handle.events.append("login_success")
        return handle

    async def mark_login_paused(self, user_id: int) -> BrowserSessionHandle | None:
        handle = await self.get_context(user_id)
        if handle is None:
            return None
        handle.meeting_state = MeetingState.PAUSED_HUMAN_INPUT
        handle.events.append("login_paused_human_input")
        return handle

    async def mark_waiting_room(self, user_id: int, course_id: int, course_name: str) -> BrowserSessionHandle | None:
        handle = await self.get_context(user_id)
        if handle is None:
            return None
        handle.meeting_state = MeetingState.WAITING_ROOM
        handle.active_course_id = course_id
        handle.active_course_name = course_name
        handle.waiting_room_since = datetime.now(UTC)
        handle.events.append("meeting_waiting_room")
        return handle

    async def mark_joined(self, user_id: int, course_id: int, course_name: str) -> BrowserSessionHandle | None:
        handle = await self.get_context(user_id)
        if handle is None:
            return None
        handle.meeting_state = MeetingState.IN_MEETING
        handle.active_course_id = course_id
        handle.active_course_name = course_name
        handle.waiting_room_since = None
        handle.events.append("meeting_joined")
        return handle

    async def mark_left(self, user_id: int) -> BrowserSessionHandle | None:
        handle = await self.get_context(user_id)
        if handle is None:
            return None
        handle.meeting_state = MeetingState.IDLE
        handle.active_course_id = None
        handle.active_course_name = None
        handle.waiting_room_since = None
        handle.events.append("meeting_left")
        return handle

    async def mark_error(self, user_id: int, message: str) -> BrowserSessionHandle | None:
        handle = await self.get_context(user_id)
        if handle is None:
            return None
        handle.meeting_state = MeetingState.ERROR
        handle.last_error = message
        handle.events.append("error")
        return handle

    async def unexpected_end(self, user_id: int) -> BrowserSessionHandle | None:
        handle = await self.get_context(user_id)
        if handle is None:
            return None
        handle.meeting_state = MeetingState.ERROR
        handle.last_error = "Meeting ended unexpectedly."
        handle.events.append("meeting_unexpected_end")
        return handle
