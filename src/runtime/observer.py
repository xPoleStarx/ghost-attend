"""Runtime observation and checkpoint emission."""

from __future__ import annotations

from datetime import datetime, timezone

from src.core.logging import get_logger

log = get_logger(__name__)


class RuntimeObserver:
    """Persists runtime decisions and sends screenshots when needed."""

    def __init__(self, notifier=None, session_repo=None, state_store=None):
        self.notifier = notifier
        self.session_repo = session_repo
        self.state_store = state_store
        self._emitted_events: set[str] = set()

    async def record_decision(self, session_id: str, entry: dict) -> None:
        if self.state_store is not None:
            self.state_store.decision_log.append(entry)
        if self.session_repo and hasattr(self.session_repo, "append_metadata_event"):
            try:
                await self.session_repo.append_metadata_event(
                    session_id,
                    "decision_log",
                    {**entry, "timestamp": datetime.now(timezone.utc).isoformat()},
                )
            except Exception as exc:
                log.warning("runtime.decision_log_failed", session_id=session_id, error=str(exc))

    async def send_runtime_screenshot(
        self,
        *,
        user_id: int,
        session_id: str,
        screenshot_bytes: bytes,
        caption: str,
    ) -> None:
        if self.notifier:
            await self.notifier.send_screenshot(
                user_id=user_id,
                screenshot_bytes=screenshot_bytes,
                caption=caption,
                checkpoint_name="runtime",
                session_id=session_id,
            )

    async def send_runtime_message(
        self,
        *,
        user_id: int,
        text: str,
    ) -> None:
        if self.notifier:
            await self.notifier.send_message(user_id=user_id, text=text)

    async def emit_progress(
        self,
        *,
        event_key: str,
        user_id: int,
        session_id: str,
        caption: str,
        screenshot_bytes: bytes | None = None,
    ) -> None:
        """Emit a progress update at most once per event key."""
        if event_key in self._emitted_events:
            return
        self._emitted_events.add(event_key)

        if screenshot_bytes:
            await self.send_runtime_screenshot(
                user_id=user_id,
                session_id=session_id,
                screenshot_bytes=screenshot_bytes,
                caption=caption,
            )
            return

        await self.send_runtime_message(user_id=user_id, text=caption)
