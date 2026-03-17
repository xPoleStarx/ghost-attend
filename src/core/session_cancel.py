"""
GhostAttend — Session Cancel Service

Kullanıcının /cancel isteğini "gerçek temizlik" sözleşmesiyle uygular:
- Agent'ı durdurmak için Redis cancel flag set eder
- MFA / session namespace key'lerini temizler
- DB'de aktif session varsa status=cancelled yapar
"""

from __future__ import annotations

from typing import Iterable

import redis.asyncio as aioredis

from src.core.constants import REDIS_PREFIX_CANCEL, REDIS_PREFIX_MFA, REDIS_PREFIX_SESSION
from src.core.logging import get_logger

log = get_logger(__name__)


async def _delete_keys(redis_client: aioredis.Redis, keys: Iterable[str]) -> int:
    key_list = [k for k in keys if k]
    if not key_list:
        return 0
    try:
        # redis-py: delete(*names) -> int
        return int(await redis_client.delete(*key_list))
    except Exception:
        # En kötü ihtimalle tek tek dene
        deleted = 0
        for k in key_list:
            try:
                deleted += int(await redis_client.delete(k))
            except Exception:
                continue
        return deleted


async def cancel_user_session(
    *,
    user_id: int,
    redis_client: aioredis.Redis | None,
    db_session=None,
) -> dict:
    """
    /cancel komutu için merkezi iptal + temizlik.

    Returns:
        {"cancel_flag_set": bool, "redis_deleted": int, "db_cancelled": bool}
    """
    cancel_flag_set = False
    redis_deleted = 0
    db_cancelled = False

    # 1) Redis: agent stop sinyali
    if redis_client:
        try:
            cancel_key = f"{REDIS_PREFIX_CANCEL}{user_id}"
            await redis_client.set(cancel_key, "1", ex=600)
            cancel_flag_set = True
        except Exception as e:
            log.warning("cancel.redis_set_failed", user_id=user_id, error=str(e))

        # 2) Redis: MFA + session namespace cleanup
        try:
            # Bilinen tekil key'ler
            mfa_key = f"{REDIS_PREFIX_MFA}{user_id}"
            deleted = await _delete_keys(redis_client, [mfa_key])
            redis_deleted += deleted

            # session namespace key'leri (scan)
            pattern = f"{REDIS_PREFIX_SESSION}{user_id}:*"
            keys = []
            async for k in redis_client.scan_iter(match=pattern, count=200):
                if isinstance(k, bytes):
                    keys.append(k.decode())
                else:
                    keys.append(str(k))
            if keys:
                redis_deleted += await _delete_keys(redis_client, keys)
        except Exception as e:
            log.warning("cancel.redis_cleanup_failed", user_id=user_id, error=str(e))

    # 3) DB: aktif session varsa cancelled yap
    if db_session is not None:
        try:
            from src.db.repositories.session import SessionRepository

            repo = SessionRepository(db_session)
            active = await repo.get_active_session(user_id)
            if active:
                await repo.update_status(active.id, "cancelled", failure_reason="cancelled_by_user")
                db_cancelled = True
        except Exception as e:
            log.warning("cancel.db_update_failed", user_id=user_id, error=str(e))

    return {
        "cancel_flag_set": cancel_flag_set,
        "redis_deleted": redis_deleted,
        "db_cancelled": db_cancelled,
    }

