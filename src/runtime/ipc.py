"""Redis-backed runtime IPC primitives."""

from __future__ import annotations

import asyncio
import base64
import json
import uuid
from datetime import datetime, timezone
from typing import Any

import redis.asyncio as aioredis

from src.core.config import settings
from src.runtime.models import RuntimeCommand, RuntimeCommandResult, RuntimeSessionRecord

RUNTIME_SESSION_KEY = "runtime:session:{session_id}"
RUNTIME_COMMAND_QUEUE = "runtime:commands:{session_id}"
RUNTIME_RESULT_KEY = "runtime:result:{command_id}"


class RuntimeIPC:
    """Coordinates live runtime state and commands through Redis."""

    def __init__(self, redis_client: aioredis.Redis):
        self.redis = redis_client

    async def register(
        self,
        *,
        session_id: str,
        user_id: int,
        status: str,
        runtime_mode: str,
        snapshot_summary: dict[str, Any] | None = None,
        capabilities: list[str] | None = None,
    ) -> RuntimeSessionRecord:
        record = RuntimeSessionRecord(
            session_id=session_id,
            user_id=user_id,
            status=status,
            runtime_mode=runtime_mode,
            last_heartbeat_at=datetime.now(timezone.utc),
            snapshot_summary=snapshot_summary or {},
            capabilities=capabilities or [],
        )
        await self.redis.set(
            RUNTIME_SESSION_KEY.format(session_id=session_id),
            record.model_dump_json(),
            ex=settings.RUNTIME_HEARTBEAT_TTL_SECONDS,
        )
        return record

    async def heartbeat(
        self,
        *,
        session_id: str,
        user_id: int,
        status: str,
        runtime_mode: str,
        snapshot_summary: dict[str, Any] | None = None,
        capabilities: list[str] | None = None,
    ) -> RuntimeSessionRecord:
        return await self.register(
            session_id=session_id,
            user_id=user_id,
            status=status,
            runtime_mode=runtime_mode,
            snapshot_summary=snapshot_summary,
            capabilities=capabilities,
        )

    async def get_session(self, session_id: str) -> RuntimeSessionRecord | None:
        raw = await self.redis.get(RUNTIME_SESSION_KEY.format(session_id=session_id))
        if not raw:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return RuntimeSessionRecord.model_validate_json(raw)

    async def clear_session(self, session_id: str) -> None:
        await self.redis.delete(RUNTIME_SESSION_KEY.format(session_id=session_id))

    async def send_command(
        self,
        *,
        session_id: str,
        command_type: str,
        payload: dict[str, Any] | None = None,
    ) -> RuntimeCommand:
        command = RuntimeCommand(
            command_id=str(uuid.uuid4()),
            session_id=session_id,
            command_type=command_type,
            payload=payload or {},
        )
        await self.redis.rpush(
            RUNTIME_COMMAND_QUEUE.format(session_id=session_id),
            command.model_dump_json(),
        )
        return command

    async def consume_command(self, session_id: str, timeout: int = 1) -> RuntimeCommand | None:
        result = await self.redis.blpop(RUNTIME_COMMAND_QUEUE.format(session_id=session_id), timeout=timeout)
        if not result:
            return None
        _, payload = result
        if isinstance(payload, bytes):
            payload = payload.decode("utf-8")
        return RuntimeCommand.model_validate_json(payload)

    async def publish_result(
        self,
        *,
        command_id: str,
        session_id: str,
        ok: bool,
        payload: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> RuntimeCommandResult:
        result = RuntimeCommandResult(
            command_id=command_id,
            session_id=session_id,
            ok=ok,
            payload=payload or {},
            error=error,
        )
        await self.redis.set(
            RUNTIME_RESULT_KEY.format(command_id=command_id),
            result.model_dump_json(),
            ex=settings.RUNTIME_IPC_TIMEOUT_SECONDS,
        )
        return result

    async def await_result(self, command_id: str, timeout_seconds: int | None = None) -> RuntimeCommandResult | None:
        timeout = timeout_seconds or settings.RUNTIME_IPC_TIMEOUT_SECONDS
        deadline = asyncio.get_running_loop().time() + timeout
        key = RUNTIME_RESULT_KEY.format(command_id=command_id)
        while asyncio.get_running_loop().time() < deadline:
            raw = await self.redis.get(key)
            if raw:
                await self.redis.delete(key)
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8")
                return RuntimeCommandResult.model_validate_json(raw)
            await asyncio.sleep(0.25)
        return None

    @staticmethod
    def encode_bytes(data: bytes) -> str:
        return base64.b64encode(data).decode("ascii")

    @staticmethod
    def decode_bytes(data: str) -> bytes:
        return base64.b64decode(data.encode("ascii"))
