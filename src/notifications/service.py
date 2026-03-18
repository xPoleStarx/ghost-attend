"""
GhostAttend — Bildirim Servisi

Telegram üzerinden bildirim gönderme: mesaj, screenshot, hata.
Tüm bildirimler bu servis üzerinden geçer (single responsibility).
architecture.md Section 12
"""

import io

from telegram import Bot, InputFile

from src.core.logging import get_logger
from src.bot.utils.safe_text import escape_md

log = get_logger(__name__)


class NotificationService:
    """
    Telegram bildirim servisi.
    Agent, scheduler ve diğer komponentler bu servisi kullanarak
    kullanıcılara bildirim gönderir.
    """

    def __init__(self, bot_token: str, bot: Bot | None = None):
        """
        Args:
            bot_token: Telegram bot token
            bot: Mevcut Bot instance (varsa)
        """
        self.bot = bot or Bot(token=bot_token)

    async def send_message(self, user_id: int, text: str, parse_mode: str = "Markdown") -> bool:
        """
        Kullanıcıya metin mesajı gönder.

        Returns:
            True: başarılı, False: başarısız
        """
        try:
            await self.bot.send_message(
                chat_id=user_id,
                text=text,
                parse_mode=parse_mode,
            )
            log.info("notification.sent", user_id=user_id, type="message")
            return True
        except Exception as e:
            log.error("notification.failed", user_id=user_id, error=str(e))
            return False

    async def send_screenshot(
        self,
        user_id: int,
        screenshot_bytes: bytes,
        caption: str = "",
        checkpoint_name: str = "",
        session_id: str = "",
    ) -> bool:
        """
        Kullanıcıya screenshot gönder.

        Args:
            screenshot_bytes: PNG screenshot verisi
            caption: Fotoğraf altı yazısı
            checkpoint_name: Checkpoint adı (loglama için)
            session_id: Session ID (loglama için)
        """
        try:
            photo = InputFile(io.BytesIO(screenshot_bytes), filename="screenshot.png")
            await self.bot.send_photo(
                chat_id=user_id,
                photo=photo,
                caption=caption[:1024],  # Telegram caption limiti
            )
            log.info(
                "notification.screenshot_sent",
                user_id=user_id,
                checkpoint=checkpoint_name,
                session_id=session_id,
            )
            return True
        except Exception as e:
            log.error("notification.screenshot_failed", user_id=user_id, error=str(e))
            return False

    async def send_error(
        self,
        user_id: int,
        error_code: str,
        details: str = "",
    ) -> bool:
        """
        Kullanıcıya hata bildirimi gönder.
        """
        error_messages = {
            "DYS_LOGIN_FAILED": "❌ DYS giriş başarısız! /reauth ile bilgilerini güncelle.",
            "LINK_NOT_FOUND": "⚠️ Ders linki DYS'te bulunamadı.",
            "MFA_REQUIRED": f"🔐 Doğrulama kodu gerekiyor.\n{details}",
            "MFA_AUTHENTICATOR": f"📱 Authenticator onayı gerekiyor.\n{details}",
            "MFA_TIMEOUT": "⏰ MFA zaman aşımı. Oturum iptal edildi.",
            "JOIN_FAILED": "❌ Derse katılım başarısız.",
            "PAGE_FROZEN": "🧊 Sayfa dondu, yeniden deneniyor...",
            "COOKIE_EXPIRED": "🍪 Oturum süresi doldu, yeniden giriş yapılacak.",
            "CREDENTIAL_NOT_FOUND": "❌ Senin için kayıtlı giriş bilgisi bulamadım. /reauth yazarak bilgilerini yeniden kaydedebilirsin.",
            "CREDENTIAL_ERROR_KEY_MISMATCH": "❌ Daha önce kaydettiğin giriş bilgilerini çözerken hata aldım. Muhtemelen sistemi yeniden kurarken anahtar değişti. /reauth ile bilgilerini yeniden kaydedelim.",
            "CREDENTIAL_ERROR": "❌ Giriş bilgilerin okunurken beklenmeyen bir hata oluştu. /reauth ile bilgilerini tazelemen iyi olur.",
            "RETRY": details,
            "AGENT_ERROR": f"⚠️ Beklenmeyen hata: {details}",
        }

        message = error_messages.get(error_code, f"⚠️ Hata: {error_code}\n{details}")

        return await self.send_message(user_id, message)

    async def send_lesson_reminder(
        self,
        user_id: int,
        course_name: str,
        start_time: str | None = None,
        minutes_before: int = 5,
    ) -> bool:
        """Ders başlamadan önce hatırlatma gönder."""
        safe_course = escape_md(course_name, version=1)
        time_line = f"Baslangic saati: {start_time}\n\n" if start_time else "\n"
        return await self.send_message(
            user_id=user_id,
            text=(
                f"⏰ *{safe_course}* dersi yaklaşık {minutes_before} dakika sonra başlayacak.\n"
                f"{time_line}"
                "Dersin başlamasına son 5 dakika. Şimdi giriş yapıyorum ve her kritik adımı sana bildireceğim."
            ),
        )

    async def send_lesson_complete(
        self,
        user_id: int,
        course_name: str,
        duration_minutes: int | None = None,
    ) -> bool:
        """Ders tamamlandı bildirimi."""
        safe_course = escape_md(course_name, version=1)
        duration_text = f"\nSüre: ~{duration_minutes} dakika" if duration_minutes else ""
        return await self.send_message(
            user_id=user_id,
            text=(
                f"✅ *{safe_course}* dersi tamamlandı!{duration_text}\n\n"
                "Detaylar için /logs yaz."
            ),
        )

    async def send_daily_summary(
        self,
        user_id: int,
        completed: list[str],
        failed: list[str],
        upcoming: list[str],
    ) -> bool:
        """Günlük özet bildirimi."""
        lines = ["📊 *Günlük Özet*\n"]

        if completed:
            lines.append("✅ *Tamamlanan:*")
            for c in completed:
                lines.append(f"  • {escape_md(c, version=1)}")

        if failed:
            lines.append("\n❌ *Başarısız:*")
            for f in failed:
                lines.append(f"  • {escape_md(f, version=1)}")

        if upcoming:
            lines.append("\n📅 *Yarınki dersler:*")
            for u in upcoming:
                lines.append(f"  • {escape_md(u, version=1)}")

        if not completed and not failed:
            lines.append("Bugün ders yoktu.")

        return await self.send_message(user_id=user_id, text="\n".join(lines))
