"""Guardrails for runtime browser actions."""

from __future__ import annotations

from src.core.exceptions import AgentJoinFailed
from src.runtime.models import BrowserElementRef


BLOCKED_ACTION_KEYWORDS = {
    "mic": "Microphone controls are blocked.",
    "microphone": "Microphone controls are blocked.",
    "camera": "Camera controls are blocked.",
    "hang up": "Leave/hang-up controls are blocked.",
    "ayril": "Leave/hang-up controls are blocked.",
    "logout": "Logout controls are blocked.",
    "oturumu kapat": "Logout controls are blocked.",
}


class RuntimeGuardrails:
    """Policy checks before runtime actions execute."""

    def assert_action_allowed(
        self,
        tool_name: str,
        *,
        element: BrowserElementRef | None = None,
        value: str | None = None,
    ) -> None:
        lowered = " ".join(
            part
            for part in [
                tool_name.casefold(),
                (element.name if element else "").casefold(),
                (element.text if element else "").casefold(),
                (value or "").casefold(),
            ]
            if part
        )
        for keyword, message in BLOCKED_ACTION_KEYWORDS.items():
            if keyword in lowered:
                raise AgentJoinFailed(message)
