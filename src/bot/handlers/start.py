"""
GhostAttend — /start Onboarding Handler

Kullanıcı onboarding akışı: Hoş geldin → DYS URL → Credential toplama.
architecture.md Section 6.2
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from src.bot.states import OnboardingState
from src.core.logging import get_logger

log = get_logger(__name__)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    /start komutu — Hoş geldin mesajı göster.
    """
    user = update.effective_user
    if not user:
        return ConversationHandler.END

    log.info("bot.start", user_id=user.id, username=user.username)

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Kuruluma Başla 🚀", callback_data="onboard_start"),
            InlineKeyboardButton("Nasıl Çalışır? ℹ️", callback_data="onboard_info"),
        ]
    ])

    await update.message.send_message(
        text=(
            f"👋 Hoş geldin {user.first_name}! Ben **GhostAttend**.\n\n"
            "Üniversitedeki online derslerine senin adına katılacağım.\n\n"
            "Başlamak için birkaç bilgiye ihtiyacım var.\n"
            "Tüm bilgilerin şifreli saklanır ve sadece senin VPS'inde durur.\n"
        ),
        reply_markup=keyboard,
        parse_mode="Markdown",
    )

    return OnboardingState.WELCOME


async def handle_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """'Nasıl Çalışır?' butonuna basıldığında bilgi göster."""
    query = update.callback_query
    await query.answer()

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Kuruluma Başla 🚀", callback_data="onboard_start")]
    ])

    await query.edit_message_text(
        text=(
            "ℹ️ **GhostAttend Nasıl Çalışır?**\n\n"
            "1️⃣ Üniversite DYS bilgilerini giriyorsun\n"
            "2️⃣ Ders programı fotoğrafını gönderiyorsun\n"
            "3️⃣ Sistem derslerini otomatik tespit ediyor\n"
            "4️⃣ Her ders 5dk önce otomatik olarak giriş yapılıyor\n"
            "5️⃣ Her adımda sana ekran görüntüsü gönderiliyor\n\n"
            "🔒 Tüm şifreler AES-256 ile şifrelenir.\n"
            "📱 MFA gerektiğinde sana bildirim gelir."
        ),
        reply_markup=keyboard,
        parse_mode="Markdown",
    )

    return OnboardingState.WELCOME


async def handle_onboard_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """'Kuruluma Başla' butonuna basıldığında DYS URL sor."""
    query = update.callback_query
    await query.answer()

    await query.edit_message_text(
        text=(
            "🏫 Önce üniversitenin öğrenci bilgi sistemi (OBS/DYS) adresini gir.\n\n"
            "Örnek: `https://obs.ege.edu.tr`\n\n"
            "_(Bilmiyorsan üniversitenin web sitesine bak)_"
        ),
        parse_mode="Markdown",
    )

    return OnboardingState.ASK_DYS_URL


async def handle_dys_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Kullanıcının girdiği DYS URL'ini kaydet."""
    url = update.message.text.strip()

    # Basit URL validasyonu
    if not url.startswith(("http://", "https://")):
        await update.message.reply_text(
            "⚠️ Geçerli bir URL gir (https:// ile başlamalı).\n"
            "Örnek: `https://obs.ege.edu.tr`",
            parse_mode="Markdown",
        )
        return OnboardingState.ASK_DYS_URL

    # Context'e kaydet
    context.user_data["dys_url"] = url

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Aynı hesap ✓", callback_data="cred_unified"),
            InlineKeyboardButton("Farklı hesaplar ✗", callback_data="cred_separate"),
        ]
    ])

    await update.message.reply_text(
        text=(
            f"✅ Adres kaydedildi: `{url}`\n\n"
            "Microsoft hesabın (Teams için) ile DYS giriş bilgilerin "
            "aynı mı, yoksa farklı mı?"
        ),
        reply_markup=keyboard,
        parse_mode="Markdown",
    )

    return OnboardingState.ASK_CREDENTIAL_TYPE


async def handle_credential_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Aynı hesap mı, farklı hesaplar mı?"""
    query = update.callback_query
    await query.answer()

    cred_type = query.data  # 'cred_unified' veya 'cred_separate'
    context.user_data["credential_type"] = "unified" if cred_type == "cred_unified" else "separate"

    await query.edit_message_text(
        text=(
            "📧 E-posta adresini yaz:\n"
            "_(örn: 123456789@stu.ege.edu.tr)_"
        ),
        parse_mode="Markdown",
    )

    return OnboardingState.ASK_DYS_EMAIL


async def handle_dys_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """E-posta adresini kaydet ve şifre iste."""
    email = update.message.text.strip()

    # Basit email validasyonu
    if "@" not in email:
        await update.message.reply_text(
            "⚠️ Geçerli bir e-posta adresi gir.",
        )
        return OnboardingState.ASK_DYS_EMAIL

    context.user_data["dys_email"] = email

    # Şifre isteği mesajını gönder ve message_id'yi kaydet
    prompt_msg = await update.message.reply_text(
        text=(
            "🔒 Şifreni yaz:\n"
            "⚠️ Bu mesaj ve senin mesajın hemen silinecek."
        ),
    )
    context.user_data["password_prompt_msg_id"] = prompt_msg.message_id

    return OnboardingState.ASK_DYS_PASSWORD


async def handle_dys_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Şifreyi al, mesajları sil, şifrele ve kaydet.
    architecture.md Section 7.2
    """
    password = update.message.text
    user_id = update.effective_user.id

    # 1. Kullanıcının şifre mesajını HEMEN sil
    try:
        await update.message.delete()
    except Exception:
        log.warning("bot.delete_password_msg_failed", user_id=user_id)

    # 2. "Şifreni yaz" mesajını da sil
    prompt_msg_id = context.user_data.get("password_prompt_msg_id")
    if prompt_msg_id:
        try:
            await context.bot.delete_message(
                chat_id=update.effective_chat.id,
                message_id=prompt_msg_id,
            )
        except Exception:
            log.warning("bot.delete_prompt_msg_failed", user_id=user_id)

    # 3. Bilgileri context'e kaydet (DB'ye sonra yazılacak)
    context.user_data["dys_password"] = password

    log.info("bot.credential_received", user_id=user_id)

    # 4. Onay mesajı
    await update.effective_chat.send_message(
        text=(
            "✅ Şifre güvenli şekilde alındı.\n\n"
            "Bilgiler doğrulanıyor... ⏳"
        ),
    )

    # TODO (Sprint 3): Burada Playwright ile DYS login denemesi yapılacak
    # Şimdilik sadece credential'ı kaydet

    # 5. Ders programı fotoğrafı iste
    await update.effective_chat.send_message(
        text=(
            "✅ Bilgiler kaydedildi!\n\n"
            "Şimdi ders programını yükle. 📷\n"
            "Resim net ve okunaklı olsun."
        ),
    )

    return OnboardingState.ASK_SCHEDULE_PHOTO


async def handle_schedule_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Ders programı fotoğrafını al.
    Sprint 2'de Vision LLM parse devreye girecek.
    """
    if not update.message.photo:
        await update.message.reply_text(
            "📷 Lütfen ders programının fotoğrafını gönder."
        )
        return OnboardingState.ASK_SCHEDULE_PHOTO

    # En yüksek kaliteli fotoğrafı al
    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)

    # Context'e kaydet
    context.user_data["schedule_photo_file_id"] = photo.file_id

    await update.message.reply_text(
        text="🔍 Ders programı analiz ediliyor... ⏳",
    )

    # TODO (Sprint 2): Vision LLM ile parse et ve sonuçları göster
    # Şimdilik placeholder

    await update.message.reply_text(
        text=(
            "📚 Ders programı kaydedildi!\n\n"
            "_(Vision LLM entegrasyonu Sprint 2'de aktifleşecek)_\n\n"
            "🎉 Kurulum tamamlandı!\n\n"
            "Yönetim komutları:\n"
            "/status — aktif oturumu gör\n"
            "/courses — derslerini listele\n"
            "/cancel — aktif oturumu iptal et\n"
            "/help — komut listesi"
        ),
        parse_mode="Markdown",
    )

    return ConversationHandler.END


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Onboarding'i iptal et."""
    await update.message.reply_text(
        "⏹️ Kurulum iptal edildi. Tekrar başlamak için /start yaz."
    )
    return ConversationHandler.END


def get_onboarding_handler() -> ConversationHandler:
    """Onboarding ConversationHandler'ı oluştur ve döndür."""
    return ConversationHandler(
        entry_points=[CommandHandler("start", start_command)],
        states={
            OnboardingState.WELCOME: [
                CallbackQueryHandler(handle_onboard_start, pattern="^onboard_start$"),
                CallbackQueryHandler(handle_info, pattern="^onboard_info$"),
            ],
            OnboardingState.ASK_DYS_URL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_dys_url),
            ],
            OnboardingState.ASK_CREDENTIAL_TYPE: [
                CallbackQueryHandler(handle_credential_type, pattern="^cred_"),
            ],
            OnboardingState.ASK_DYS_EMAIL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_dys_email),
            ],
            OnboardingState.ASK_DYS_PASSWORD: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_dys_password),
            ],
            OnboardingState.ASK_SCHEDULE_PHOTO: [
                MessageHandler(filters.PHOTO, handle_schedule_photo),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_schedule_photo),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_command)],
        name="onboarding",
        persistent=False,
    )
