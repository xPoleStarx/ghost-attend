"""Snapshot-driven browser control service."""

from __future__ import annotations

import asyncio
import base64
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from src.core.logging import get_logger
from src.runtime.models import BrowserElementRef, BrowserSnapshot

log = get_logger(__name__)


SNAPSHOT_JS = """
() => {
  const visible = (el) => {
    const style = window.getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    return style.visibility !== 'hidden' && style.display !== 'none' && rect.width > 0 && rect.height > 0;
  };
  const cssPath = (el) => {
    if (!(el instanceof Element)) return null;
    const parts = [];
    let node = el;
    while (node && node.nodeType === Node.ELEMENT_NODE && parts.length < 6) {
      let selector = node.nodeName.toLowerCase();
      if (node.id) {
        selector += `#${CSS.escape(node.id)}`;
        parts.unshift(selector);
        break;
      }
      const role = node.getAttribute('role');
      if (role) selector += `[role="${role}"]`;
      const siblings = node.parentElement ? Array.from(node.parentElement.children).filter((sib) => sib.nodeName === node.nodeName) : [];
      if (siblings.length > 1) selector += `:nth-of-type(${siblings.indexOf(node) + 1})`;
      parts.unshift(selector);
      node = node.parentElement;
    }
    return parts.join(' > ');
  };
  const nodes = Array.from(document.querySelectorAll('a,button,input,textarea,select,[role],summary,[contenteditable="true"]'));
  return nodes
    .filter((el) => visible(el))
    .slice(0, 200)
    .map((el, index) => {
      const rect = el.getBoundingClientRect();
      return {
        ref: `e${index + 1}`,
        role: el.getAttribute('role') || el.tagName.toLowerCase(),
        name: el.getAttribute('aria-label') || el.getAttribute('name') || el.getAttribute('placeholder') || '',
        text: (el.innerText || el.textContent || '').trim().slice(0, 160),
        selector: cssPath(el),
        clickable: ['a', 'button', 'summary'].includes(el.tagName.toLowerCase()) || el.onclick !== null || el.getAttribute('role') === 'button',
        editable: ['input', 'textarea', 'select'].includes(el.tagName.toLowerCase()) || el.isContentEditable,
        disabled: !!el.disabled || el.getAttribute('aria-disabled') === 'true',
        bounds: {x: rect.x, y: rect.y, width: rect.width, height: rect.height},
      };
    });
}
"""


@dataclass
class BrowserSession:
    """A single browser session."""

    session_id: str
    page: Any
    context: Any = None
    browser: Any = None
    tab_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    snapshot_cache: dict[str, BrowserElementRef] = field(default_factory=dict)
    console_events: list[str] = field(default_factory=list)
    network_events: list[str] = field(default_factory=list)
    current_snapshot_id: str | None = None


class BrowserControlService:
    """Captures snapshots and executes ref-based browser actions."""

    def __init__(self) -> None:
        self._sessions: dict[str, BrowserSession] = {}

    def attach_session(self, session: BrowserSession) -> None:
        self._sessions[session.session_id] = session
        self._attach_event_listeners(session)

    def get_session(self, session_id: str) -> BrowserSession:
        return self._sessions[session_id]

    def detach_session(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    def _attach_event_listeners(self, session: BrowserSession) -> None:
        page = session.page
        try:
            page.on("console", lambda msg: session.console_events.append(str(getattr(msg, "text", msg))[:200]))
            page.on("requestfinished", lambda req: session.network_events.append(str(getattr(req, "url", ""))[:200]))
        except Exception:
            pass

    async def snapshot(self, session_id: str, fmt: str = "role") -> BrowserSnapshot:
        session = self.get_session(session_id)
        page = session.page
        elements_raw = []
        title = ""
        url = ""
        page_signals: dict[str, Any] = {}
        try:
            elements_raw = await page.evaluate(SNAPSHOT_JS)
            title = await page.title()
            url = page.url
            body_text = await page.locator("body").inner_text()
            body_lower = body_text.casefold()[:3000]
            page_signals = {
                "login_form_detected": any(token in body_lower for token in ["giris", "login", "password", "sifre"]),
                "meeting_ui_detected": any(token in body_lower for token in ["join", "katil", "meeting", "toplanti"]),
                "mfa_prompt_detected": any(token in body_lower for token in ["verification code", "dogrulama", "authenticator", "sms"]),
                "modal_present": "dialog" in body_lower or "modal" in body_lower,
            }
        except Exception as exc:
            log.warning("runtime.snapshot_failed", session_id=session_id, error=str(exc))

        elements = [BrowserElementRef.model_validate(item) for item in elements_raw]
        snapshot_id = uuid.uuid4().hex
        session.snapshot_cache = {item.ref: item for item in elements}
        session.current_snapshot_id = snapshot_id
        return BrowserSnapshot(
            snapshot_id=snapshot_id,
            tab_id=session.tab_id,
            url=url,
            title=title,
            timestamp=datetime.now(timezone.utc),
            format="role" if fmt not in {"role", "aria", "dom-lite"} else fmt,
            elements=elements,
            page_signals=page_signals,
        )

    async def screenshot(self, session_id: str) -> bytes:
        session = self.get_session(session_id)
        return await session.page.screenshot(type="png", full_page=False)

    async def click(self, session_id: str, ref: str) -> dict[str, Any]:
        session = self.get_session(session_id)
        element = self._require_element(session, ref)
        await session.page.locator(element.selector).click()
        return {"clicked": ref}

    async def type(self, session_id: str, ref: str, text: str) -> dict[str, Any]:
        session = self.get_session(session_id)
        element = self._require_element(session, ref)
        locator = session.page.locator(element.selector)
        await locator.fill(text)
        return {"typed": ref, "text": text}

    async def press(self, session_id: str, key: str) -> dict[str, Any]:
        session = self.get_session(session_id)
        await session.page.keyboard.press(key)
        return {"pressed": key}

    async def navigate(self, session_id: str, url: str) -> dict[str, Any]:
        session = self.get_session(session_id)
        await session.page.goto(url)
        return {"url": url}

    async def evaluate(self, session_id: str, expression: str) -> dict[str, Any]:
        session = self.get_session(session_id)
        value = await session.page.evaluate(expression)
        safe_value = value
        if isinstance(value, bytes):
            safe_value = base64.b64encode(value).decode()
        return {"value": safe_value}

    async def wait_for(self, session_id: str, milliseconds: int) -> dict[str, Any]:
        await asyncio.sleep(max(milliseconds, 0) / 1000)
        return {"waited_ms": milliseconds}

    async def network_summary(self, session_id: str) -> dict[str, Any]:
        session = self.get_session(session_id)
        return {"recent_requests": session.network_events[-20:]}

    async def console_summary(self, session_id: str) -> dict[str, Any]:
        session = self.get_session(session_id)
        return {"recent_console": session.console_events[-20:]}

    def _require_element(self, session: BrowserSession, ref: str) -> BrowserElementRef:
        if ref not in session.snapshot_cache:
            raise ValueError(f"Unknown or stale ref: {ref}")
        element = session.snapshot_cache[ref]
        if not element.selector:
            raise ValueError(f"Ref {ref} has no selector")
        return element
