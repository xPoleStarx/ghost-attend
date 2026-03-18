"""In-memory runtime registry for active sessions."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RuntimeRegistry:
    """Tracks active runtime engines inside the current process."""

    _by_user: dict[int, object]
    _by_session: dict[str, object]

    def __init__(self) -> None:
        self._by_user = {}
        self._by_session = {}

    def register(self, user_id: int, session_id: str, runtime: object) -> None:
        self._by_user[user_id] = runtime
        self._by_session[session_id] = runtime

    def unregister(self, user_id: int, session_id: str) -> None:
        self._by_user.pop(user_id, None)
        self._by_session.pop(session_id, None)

    def get_by_user(self, user_id: int) -> object | None:
        return self._by_user.get(user_id)

    def get_by_session(self, session_id: str) -> object | None:
        return self._by_session.get(session_id)


runtime_registry = RuntimeRegistry()
