from __future__ import annotations

import base64
import logging
from typing import TYPE_CHECKING

from langchain_core.tools import tool
from langgraph.config import get_config
from langgraph.types import interrupt

from app.adapters.browser_use_runner import BrowserUseRunner
from app.adapters.screenshot import capture_url_png
from app.agent.media_delivery import stash_screenshot_png
from app.domain.schemas import BrowserRunStatus

if TYPE_CHECKING:
    from app.config.settings import Settings

logger = logging.getLogger(__name__)


def _thread_id_from_context() -> str:
    try:
        cfg = get_config()
        tid = cfg.get("configurable", {}).get("thread_id")
        return str(tid) if tid is not None else "default"
    except RuntimeError:
        return "default"


def build_task_tools(settings: "Settings"):
    """Gemini'nin bağlayacağı araçlar (closure ile Settings)."""

    @tool
    async def capture_page_screenshot(url: str) -> str:
        """Take a PNG screenshot of a single http(s) page (public, no login session)."""
        tid = _thread_id_from_context()
        try:
            png = await capture_url_png(url.strip(), headless=settings.playwright_headless)
        except Exception:
            logger.exception("capture_page_screenshot failed for %s", url)
            return f"Screenshot failed for {url}."
        stash_screenshot_png(tid, png)
        return f"Screenshot captured for {url}. The image will be sent to the user in Telegram."

    @tool
    async def ask_user(question: str) -> str:
        """Ask the user for a password, 2FA/OTP code, or clarification. Use instead of guessing."""
        value = interrupt({"question": question.strip()})
        return f"User replied: {value!s}"

    @tool
    async def run_browser_automation(task: str) -> str:
        """Use for ANY real website workflow (open URL, click menus, student login, screenshots after navigation).

        Pass one detailed instruction: starting URL, exact clicks/menus, and goal (e.g. screenshot of schedule page).
        Do not skip this tool to answer about CAPTCHA or "manual login" — run first, then interpret the result.
        The embedded agent may pause to ask the user for credentials via Telegram."""
        runner = BrowserUseRunner(settings)
        instruction = task.strip()
        hints: list[str] = []
        tid = _thread_id_from_context()

        while True:
            result = await runner.run_task(instruction, hints, thread_id=tid)
            if result.status == BrowserRunStatus.NEEDS_HUMAN:
                shot_b64: str | None = None
                if result.screenshot_png:
                    shot_b64 = base64.b64encode(result.screenshot_png).decode("ascii")
                resume_value = interrupt(
                    {
                        "question": result.question or "More information needed to continue.",
                        "screenshot_png_b64": shot_b64,
                        "last_url": result.last_url,
                        "photo_caption": "Tarayıcı ekranı — yukarıdaki metni oku, ardından yanıt ver.",
                    }
                )
                text = str(resume_value).strip() if resume_value is not None else ""
                if text:
                    hints.append(text)
                continue
            if result.status == BrowserRunStatus.ERROR:
                msg = result.summary
                if result.raw_error:
                    msg = f"{msg}\nTechnical: {result.raw_error}"
                return msg
            if result.screenshot_png:
                stash_screenshot_png(tid, result.screenshot_png)
            summary = (result.summary or "Task finished.").strip()
            return summary

    return [capture_page_screenshot, ask_user, run_browser_automation]
