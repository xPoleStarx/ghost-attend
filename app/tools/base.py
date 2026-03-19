from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from app.domain.schemas import ToolResult


class ToolExecutionMixin:
    async def execute_with_timeout(
        self, timeout_seconds: int, operation: Callable[[], Awaitable[ToolResult]]
    ) -> ToolResult:
        try:
            return await asyncio.wait_for(operation(), timeout=timeout_seconds)
        except TimeoutError:
            return ToolResult(success=False, message="Tool timed out.", screenshot_path=None)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(success=False, message=str(exc), screenshot_path=None)
