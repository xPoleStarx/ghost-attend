from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class RouteIntent(StrEnum):
    SCREENSHOT = "screenshot"
    BROWSER = "browser"
    CHAT = "chat"


class BrowserRunStatus(StrEnum):
    DONE = "done"
    NEEDS_HUMAN = "needs_human"
    ERROR = "error"


@dataclass
class ScreenshotArtifact:
    png_bytes: bytes
    caption: str
    url: str | None = None


@dataclass
class BrowserRunResult:
    status: BrowserRunStatus
    summary: str
    last_url: str | None = None
    screenshot_png: bytes | None = None
    question: str | None = None
    history_tail: str | None = None
    raw_error: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class HitlPayload:
    """Telegram'a iletilen interrupt yükü (loglarda ham PNG yok)."""

    question: str
    reason: str
    screenshot_png: bytes | None = None
