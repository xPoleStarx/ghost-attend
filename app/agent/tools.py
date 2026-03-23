from __future__ import annotations

import base64
import logging
from typing import TYPE_CHECKING

from langchain_core.tools import tool
from langgraph.config import get_config
from langgraph.types import interrupt

from app.adapters.browser_use_runner import (
    BrowserUseRunner,
    infer_reply_language,
    parse_reply_lang_directive,
)
from app.adapters.screenshot import capture_url_png
from app.agent.media_delivery import stash_screenshot_png
from app.domain.schemas import BrowserRunResult, BrowserRunStatus

if TYPE_CHECKING:
    from app.config.settings import Settings

logger = logging.getLogger(__name__)

_HITL_TAIL_MAX = 4000


def _hitl_reason_label(reason: str | None) -> str:
    if not reason:
        return "unknown"
    if reason == "login_or_auth_surface":
        return "login or identity screen"
    if reason == "model_indicated_sensitive_step":
        return "sensitive step (password, OTP, 2FA, etc.)"
    if reason == "repeated_auth_failure":
        return "repeated login/auth failure"
    if reason == "user_mid_run_message":
        return "user message during browser run"
    return str(reason)


def _continuation_block_after_hitl(result: BrowserRunResult) -> str:
    tail = (result.history_tail or "").strip()
    if len(tail) > _HITL_TAIL_MAX:
        tail = tail[:_HITL_TAIL_MAX] + "\n…[truncated]"
    lines = [
        "[Auto-resume context — right after interrupt]",
        f"Stop reason: {_hitl_reason_label(result.hitl_reason)}",
        f"Last URL: {result.last_url or '(unknown)'}",
        "Last agent output / summary:",
        tail or "(none)",
        "",
        "Rules: Do not re-run numbered steps from the beginning; use the current page and session. "
        "Move only toward the remaining goal; avoid redundant navigation.",
    ]
    return "\n".join(lines)


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

        Start with a first line `[reply-lang:tr]` or `[reply-lang:en]` matching the user's chat language, then a blank line, then the task (URLs, steps, credentials).
        Do not skip this tool to answer about CAPTCHA or "manual login" — run first, then interpret the result.
        The embedded agent may pause to ask the user for credentials via Telegram."""
        runner = BrowserUseRunner(settings)
        forced_lang, instruction = parse_reply_lang_directive(task.strip())
        hints: list[str] = []
        tid = _thread_id_from_context()

        while True:
            # İlk tur: [reply-lang:…] varsa onu kullan. HITL sonrası ipuçlarında kullanıcı dili baskınsa yeniden çıkar.
            lang_kw: str | None = forced_lang if not hints else None
            result = await runner.run_task(
                instruction,
                hints,
                thread_id=tid,
                reply_lang=lang_kw,
            )
            if result.status == BrowserRunStatus.NEEDS_HUMAN:
                shot_b64: str | None = None
                if result.screenshot_png:
                    shot_b64 = base64.b64encode(result.screenshot_png).decode("ascii")
                ulang = forced_lang or infer_reply_language(
                    instruction + "\n" + "\n".join(h.strip() for h in hints if h.strip())
                )
                caption = (
                    "Tarayıcı ekranı — yukarıdaki metni oku, ardından yanıt ver."
                    if ulang == "tr"
                    else "Browser view — read the text above, then reply."
                )
                resume_value = interrupt(
                    {
                        "question": result.question or "More information needed to continue.",
                        "screenshot_png_b64": shot_b64,
                        "last_url": result.last_url,
                        "photo_caption": caption,
                    }
                )
                text = str(resume_value).strip() if resume_value is not None else ""
                if text:
                    hints.append(text)
                else:
                    empty = (
                        "[User reply was empty; continue on the current browser page and session.]"
                        if ulang != "tr"
                        else "[Kullanıcı yanıtı boş; mevcut tarayıcı sayfasında ve oturumda devam et.]"
                    )
                    hints.append(empty)
                hints.append(_continuation_block_after_hitl(result))
                continue
            if result.status == BrowserRunStatus.ERROR:
                msg = result.summary
                if result.raw_error:
                    msg = f"{msg}\nTechnical: {result.raw_error}"
                return msg
            if result.status == BrowserRunStatus.CANCELLED:
                return (
                    f"[User stopped the browser task] {result.summary or 'Stopped.'}"
                )
            if result.screenshot_png:
                stash_screenshot_png(tid, result.screenshot_png)
            summary = (result.summary or "Task finished.").strip()
            return summary

    return [capture_page_screenshot, ask_user, run_browser_automation]
