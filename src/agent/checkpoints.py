"""
GhostAttend — Checkpoint Handler

Agent çalışırken her kritik adımda screenshot alıp kullanıcıya gönderir.
browser-use callback hook'ları ile entegre çalışır.
architecture.md Section 9.3
"""

import io
from datetime import datetime, timezone

from src.core.constants import (
    CHECKPOINT_COMPLETED,
    CHECKPOINT_DYS_LOGIN,
    CHECKPOINT_JOINED,
    CHECKPOINT_LINK_FOUND,
)
from src.core.logging import get_logger

log = get_logger(__name__)

# Checkpoint tanımları
CHECKPOINTS: dict[str, dict[str, str]] = {
    CHECKPOINT_DYS_LOGIN: {
        "message": "✅ DYS'ye başarıyla giriş yapıldı.",
        "emoji": "🔐",
    },
    CHECKPOINT_LINK_FOUND: {
        "message": "🔗 Ders linki bulundu, Teams'e yönleniliyor...",
        "emoji": "🔗",
    },
    CHECKPOINT_JOINED: {
        "message": "🎓 Derse başarıyla katıldın! Ders süresince burada olacağım.",
        "emoji": "🎓",
    },
    CHECKPOINT_COMPLETED: {
        "message": "✅ Ders tamamlandı. Oturum kapatılıyor.",
        "emoji": "✅",
    },
}


class CheckpointHandler:
    """
    Agent step callback'i — her adımda checkpoint tespiti yapar.
    Checkpoint tespit edildiğinde screenshot alır ve Telegram'a gönderir.
    """

    def __init__(
        self,
        session_id: str,
        user_id: int,
        notifier=None,
        session_repo=None,
    ):
        self.session_id = session_id
        self.user_id = user_id
        self.notifier = notifier
        self.session_repo = session_repo
        self.detected_checkpoints: list[str] = []

    async def handle_step(self, step_info: dict) -> None:
        """
        browser-use agent'ın her adımında çağrılır.
        Step output'unu kontrol ederek checkpoint tetikler.

        Args:
            step_info: browser-use step callback verisi
        """
        step_text = str(step_info.get("output", ""))
        step_number = step_info.get("step_number", 0)

        log.info(
            "agent.step",
            session_id=self.session_id,
            step=step_number,
            output_preview=step_text[:100],
        )

        # Checkpoint tespiti
        for checkpoint_name in CHECKPOINTS:
            if checkpoint_name in step_text and checkpoint_name not in self.detected_checkpoints:
                await self._trigger_checkpoint(
                    checkpoint_name=checkpoint_name,
                    step_info=step_info,
                )
                self.detected_checkpoints.append(checkpoint_name)

        # Hata kodu tespiti
        error_codes = [
            "HATA_KODU: DYS_LOGIN_FAILED",
            "HATA_KODU: LINK_NOT_FOUND",
            "HATA_KODU: MFA_REQUIRED",
            "HATA_KODU: JOIN_FAILED",
            "HATA_KODU: PAGE_FROZEN",
            "HATA_KODU: COOKIE_EXPIRED",
            "HATA_KODU: MEETING_NOT_STARTED",
        ]

        for error_code in error_codes:
            if error_code in step_text:
                code = error_code.replace("HATA_KODU: ", "")
                log.warning(
                    "agent.error_code_detected",
                    session_id=self.session_id,
                    error_code=code,
                )

    async def _trigger_checkpoint(
        self,
        checkpoint_name: str,
        step_info: dict,
    ) -> None:
        """Checkpoint tetiklendiğinde screenshot al ve bildirim gönder."""
        checkpoint = CHECKPOINTS.get(checkpoint_name, {})
        message = checkpoint.get("message", f"Checkpoint: {checkpoint_name}")
        emoji = checkpoint.get("emoji", "📸")

        log.info(
            "agent.checkpoint",
            session_id=self.session_id,
            checkpoint=checkpoint_name,
        )

        # Screenshot al (browser-use step_info'dan)
        screenshot_bytes = step_info.get("screenshot")

        # Telegram'a gönder
        if self.notifier:
            try:
                if screenshot_bytes:
                    await self.notifier.send_screenshot(
                        user_id=self.user_id,
                        screenshot_bytes=screenshot_bytes,
                        caption=f"{emoji} {message}",
                        checkpoint_name=checkpoint_name,
                        session_id=self.session_id,
                    )
                else:
                    await self.notifier.send_message(
                        user_id=self.user_id,
                        text=f"{emoji} {message}",
                    )
            except Exception as e:
                log.error(
                    "agent.checkpoint_notify_failed",
                    error=str(e),
                    checkpoint=checkpoint_name,
                )

        # DB'ye kaydet
        if self.session_repo:
            try:
                await self.session_repo.add_checkpoint(
                    session_id=self.session_id,
                    checkpoint_name=checkpoint_name,
                    metadata={
                        "step": step_info.get("step_number"),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                )
            except Exception as e:
                log.error("agent.checkpoint_save_failed", error=str(e))

    async def send_manual_screenshot(
        self,
        screenshot_bytes: bytes,
        caption: str,
    ) -> None:
        """Manuel olarak screenshot gönder (checkpoint dışı durumlar için)."""
        if self.notifier:
            await self.notifier.send_screenshot(
                user_id=self.user_id,
                screenshot_bytes=screenshot_bytes,
                caption=caption,
                checkpoint_name="manual",
                session_id=self.session_id,
            )
