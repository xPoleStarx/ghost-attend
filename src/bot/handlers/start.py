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

    await update.message.reply_text(
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
    Ders programı fotoğrafını al, Vision LLM (Gemini) ile parse edip onay ekranı sun.
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

    processing_msg = await update.message.reply_text(
        text="🔍 Ders programı analiz ediliyor... ⏳",
    )

    from src.vision.schedule_parser import format_courses_for_telegram, parse_schedule_image

    try:
        # Fotoğrafı indir
        image_bytes = await file.download_as_bytearray()

        # Vision LLM ile parse et
        result = await parse_schedule_image(
            image_bytes=bytes(image_bytes),
            mime_type="image/jpeg",
        )

        # Sonuçları context'e kaydet
        context.user_data["parsed_courses"] = [c.model_dump() for c in result.courses]
        context.user_data["parse_warnings"] = result.parse_warnings

        # İşleniyor mesajını sil
        try:
            await processing_msg.delete()
        except Exception:
            pass

        if not result.courses:
            await update.message.reply_text(
                "❌ Ders programından hiç ders tespit edilemedi.\n"
                "Lütfen daha net bir fotoğraf gönder veya /cancel ile iptal et."
            )
            return OnboardingState.ASK_SCHEDULE_PHOTO

        # Sonuçları göster
        text = format_courses_for_telegram(result)

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("Tümünü Onayla ✅", callback_data="onboard_confirm_all"),
                InlineKeyboardButton("Baştan Al 🔄", callback_data="onboard_restart"),
            ],
            [
                InlineKeyboardButton("Devam et (Düzenleme /courses'da)", callback_data="onboard_confirm_all"),
            ]
        ])

        await update.message.reply_text(
            text=text,
            reply_markup=keyboard,
            parse_mode="Markdown",
        )

        return OnboardingState.CONFIRM_COURSES

    except Exception as e:
        log.error("bot.schedule_parse_failed", error=str(e))
        try:
            await processing_msg.delete()
        except Exception:
            pass

        await update.message.reply_text(
            f"❌ Ders programı analiz edilirken bir hata oluştu.\n"
            f"Tekrar dene veya /cancel ile iptal et.\n\n"
            f"_Hata: {str(e)[:100]}_",
            parse_mode="Markdown",
        )
        return OnboardingState.ASK_SCHEDULE_PHOTO


async def handle_onboard_confirm_all(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Tüm dersleri onayla ve kurulumu tamamla."""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    courses = context.user_data.get("parsed_courses", [])
    course_count = len(courses)

    if courses:
        from src.db.connection import get_session
        from src.db.repositories.course import CourseRepository
        from src.db.repositories.user import UserRepository
        from src.scheduler.lesson_scheduler import schedule_all_courses_for_user

        try:
            async with get_session() as session:
                # 1. Kullanıcının veritabanında olduğundan emin ol (Eğer henüz yoksa)
                user_repo = UserRepository(session)
                user = await user_repo.get_by_id(user_id)
                if not user:
                    await user_repo.create_or_update(
                        user_id=user_id,
                        first_name=update.effective_user.first_name,
                        username=update.effective_user.username
                    )
                    await session.commit()

                # 2. Dersleri DB'ye kaydet
                course_repo = CourseRepository(session)
                await course_repo.bulk_create_from_parsed(user_id=user_id, parsed_courses=courses)
                await session.commit()

            # 3. Dersleri Redis üzerinden APScheduler'a ekle
            scheduled_jobs = await schedule_all_courses_for_user(user_id)
            log.info("bot.onboard_courses_scheduled", user_id=user_id, count=len(scheduled_jobs))

        except Exception as e:
            log.error("bot.onboard_db_schedule_failed", user_id=user_id, error=str(e))
            await query.edit_message_text(
                "❌ Dersler kaydedilirken bir veritabanı hatası oluştu. Lütfen yöneticinize başvurun."
            )
            return ConversationHandler.END

    await query.edit_message_text(
        text=(
            f"🎉 Harika! **{course_count} ders** başarıyla veritabanına kaydedildi ve zamanlandı.\n\n"
            "Sistem her ders başlamadan 5 dakika önce otomatik olarak "
            "harekete geçecek. Derse girildiğinde sana bildirim göndereceğim.\n\n"
            "Eğer bir dersi düzenlemek istersen `/courses` komutunu kullanabilirsin.\n\n"
            "Yönetim komutları:\n"
            "/status — aktif oturumu ve zamanlanmış derslerini gör\n"
            "/cancel — aktif oturumu iptal et\n"
            "/courses — derslerini listele\n"
            "/help — komut listesi\n"
            "/reauth — kimlik doğrulamayı yenile"
        ),
        parse_mode="Markdown",
    )
    return ConversationHandler.END


async def handle_onboard_restart(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ders programı yüklemeyi baştan al."""
    query = update.callback_query
    await query.answer()

    context.user_data.pop("parsed_courses", None)
    context.user_data.pop("parse_warnings", None)

    await query.edit_message_text(
        "📷 Yeni ders programı fotoğrafını gönder."
    )
    return OnboardingState.ASK_SCHEDULE_PHOTO


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
            OnboardingState.CONFIRM_COURSES: [
                CallbackQueryHandler(handle_onboard_confirm_all, pattern="^onboard_confirm_all$"),
                CallbackQueryHandler(handle_onboard_restart, pattern="^onboard_restart$"),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_command)],
        name="onboarding",
        persistent=False,
    )
