"""
GhostAttend — Bot Middleware

Auth kontrolü ve rate limiting.
"""

from telegram import Update
from telegram.ext import ContextTypes

from src.core.logging import get_logger

log = get_logger(__name__)


async def auth_middleware(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Basit auth middleware.
    Şimdilik tüm kullanıcılara izin verir.
    İleride allowlist/blocklist eklenebilir.

    Returns:
        True: devam et, False: durdur
    """
    if not update.effective_user:
        return False

    # Rate limiting kontrolü
    user_id = update.effective_user.id
    rate_key = f"rate:{user_id}"

    # TODO: Redis ile gerçek rate limiting implementasyonu
    # Şimdilik basit in-memory zamanlama
    import time

    last_request = context.user_data.get("_last_request_time", 0)
    current_time = time.time()

    # 1 saniyede 1 istek limiti
    if current_time - last_request < 0.5:
        log.warning("bot.rate_limited", user_id=user_id)
        return False

    context.user_data["_last_request_time"] = current_time

    return True
