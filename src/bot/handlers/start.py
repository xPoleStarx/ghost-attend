"""
GhostAttend — /start Onboarding Handler

Kullanıcı onboarding akışı: Hoş geldin → DYS URL → Credential toplama.
Multi-input (çoklu fotoğraf + metin) desteği ile ders programı yükleme.
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

from sqlalchemy.exc import SQLAlchemyError

from src.bot.states import OnboardingState
from src.bot.utils.safe_text import escape_dynamic_text
from src.core.logging import get_logger

log = get_logger(__name__)

# ── Done keywords ──
_DONE_KEYWORDS = {"bitti", "tamam", "done", "bitir", "gönder", "analiz et", "tamamdır"}


def _init_buffers(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Input buffer'larını başlat."""
    if "input_images" not in context.user_data:
        context.user_data["input_images"] = []
    if "input_texts" not in context.user_data:
        context.user_data["input_texts"] = []


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
            "2️⃣ Ders programı fotoğraflarını/metin bilgisini gönderiyorsun\n"
            "3️⃣ Sistem derslerini otomatik tespit ediyor\n"
            "4️⃣ Online dersleri chatbot ile düzenleyebilirsin\n"
            "5️⃣ Her ders 5dk önce otomatik olarak giriş yapılıyor\n"
            "6️⃣ Her adımda sana ekran görüntüsü gönderiliyor\n\n"
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
            f"✅ Adres kaydedildi: `{escape_dynamic_text(url, parse_mode='Markdown')}`\n\n"
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

    from src.db.connection import get_session
    from src.db.repositories.user import UserRepository
    from src.core.config import settings
    from src.security.encryption import CredentialVault
    from src.security.vault import VaultService

    try:
        async with get_session() as session:
            user_repo = UserRepository(session)
            # Kullanıcıyı oluştur/güncelle
            await user_repo.create_or_update(
                user_id=user_id,
                first_name=update.effective_user.first_name,
                username=update.effective_user.username,
            )
            # Credential'ı kaydet (PBKDF2 türetilen key ile VaultService üzerinden)
            vault = CredentialVault(settings.MASTER_ENCRYPTION_KEY)
            vault_service = VaultService(session, vault)
            await vault_service.save_credentials(
                user_id=user_id,
                credential_type="unified",
                email=context.user_data["dys_email"],
                password=password,
                dys_url=context.user_data.get("dys_url"),
            )
            await session.commit()
    except SQLAlchemyError as e:
        log.error("bot.onboard_creds_db_failed", user_id=user_id, error=str(e), exc_info=True)
        await update.effective_chat.send_message("❌ Bilgiler kaydedilirken bir hata oluştu.")
        return ConversationHandler.END
    except Exception as e:
        log.error("bot.onboard_creds_failed", user_id=user_id, error=str(e), exc_info=True)
        await update.effective_chat.send_message("❌ Bilgiler kaydedilirken bir hata oluştu.")
        return ConversationHandler.END

    log.info("bot.credential_received", user_id=user_id)

    # 4. Onay mesajı
    await update.effective_chat.send_message(
        text=(
            "✅ Kimlik bilgileri güvenli şekilde şifrelendi ve kaydedildi.\n\n"
            "Bilgiler doğrulanıyor... ⏳"
        ),
    )

    # 5. Ders programı fotoğrafı iste (multi-input)
    _init_buffers(context)
    await update.effective_chat.send_message(
        text=(
            "✅ Bilgiler kaydedildi!\n\n"
            "Şimdi ders programını yükle. 📷\n"
            "Birden fazla fotoğraf ve/veya metin gönderebilirsin.\n"
            "Tamamlanınca *bitti* yaz."
        ),
        parse_mode="Markdown",
    )

    return OnboardingState.ASK_SCHEDULE_PHOTO


async def handle_schedule_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Fotoğraf geldiğinde buffer'a ekle."""
    _init_buffers(context)

    if not update.message.photo:
        # Metin geldi — done keyword mı?
        text = update.message.text.strip() if update.message.text else ""
        if text.lower() in _DONE_KEYWORDS:
            return await _start_onboard_analysis(update, context)

        # Metin buffer'a ekle
        context.user_data["input_texts"].append(text)
        count = len(context.user_data.get("input_images", []))
        text_count = len(context.user_data["input_texts"])
        status = []
        if count:
            status.append(f"📷 {count} fotoğraf")
        status.append(f"📝 {text_count} metin")

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("Analiz Et ✅", callback_data="onboard_analyze")]
        ])
        await update.message.reply_text(
            f"✅ Metin alındı! ({', '.join(status)})\n"
            "Başka fotoğraf/metin gönderebilirsin. Tamamlanınca *bitti* yaz.",
            reply_markup=keyboard,
            parse_mode="Markdown",
        )
        return OnboardingState.ASK_SCHEDULE_PHOTO

    # Fotoğraf buffer'a ekle
    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    image_bytes = await file.download_as_bytearray()
    context.user_data["input_images"].append((bytes(image_bytes), "image/jpeg"))

    count = len(context.user_data["input_images"])
    text_count = len(context.user_data.get("input_texts", []))
    status = [f"📷 {count} fotoğraf"]
    if text_count:
        status.append(f"📝 {text_count} metin")

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Analiz Et ✅", callback_data="onboard_analyze")]
    ])

    await update.message.reply_text(
        f"✅ Alındı! ({', '.join(status)})\n"
        "Başka fotoğraf/metin gönderebilirsin. Tamamlanınca *bitti* yaz.",
        reply_markup=keyboard,
        parse_mode="Markdown",
    )
    return OnboardingState.ASK_SCHEDULE_PHOTO


async def handle_onboard_analyze(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """'Analiz Et' callback — analiz başlat."""
    query = update.callback_query
    await query.answer()
    return await _start_onboard_analysis(update, context, from_callback=True)


async def _start_onboard_analysis(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    from_callback: bool = False,
) -> int:
    """Buffer'daki input'ları LLM'e gönder."""
    _init_buffers(context)
    images = context.user_data.get("input_images", [])
    texts = context.user_data.get("input_texts", [])

    if not images and not texts:
        msg = "📷 Henüz fotoğraf veya metin göndermedin."
        if from_callback:
            await update.callback_query.edit_message_text(msg)
        else:
            await update.message.reply_text(msg)
        return OnboardingState.ASK_SCHEDULE_PHOTO

    chat = update.effective_chat
    processing_msg = await chat.send_message("🔍 Ders programı analiz ediliyor... ⏳")

    from src.vision.schedule_parser import format_courses_for_telegram, parse_schedule_images

    try:
        extra_text = "\n".join(texts) if texts else None
        result = await parse_schedule_images(images=images, extra_text=extra_text)

        context.user_data["parsed_courses"] = [c.model_dump() for c in result.courses]
        context.user_data["parse_warnings"] = result.parse_warnings
        context.user_data.pop("input_images", None)
        context.user_data.pop("input_texts", None)

        try:
            await processing_msg.delete()
        except Exception:
            pass

        if not result.courses:
            await chat.send_message(
                "❌ Ders programından hiç ders tespit edilemedi.\n"
                "Lütfen daha net fotoğraf/metin gönder veya /cancel ile iptal et."
            )
            _init_buffers(context)
            return OnboardingState.ASK_SCHEDULE_PHOTO

        text = format_courses_for_telegram(result)

        has_online = any(c.online_mi is True for c in result.courses)
        has_uncertain = any(c.online_mi is None for c in result.courses)

        buttons = [
            [
                InlineKeyboardButton("Tümünü Onayla ✅", callback_data="onboard_confirm_all"),
                InlineKeyboardButton("Baştan Al 🔄", callback_data="onboard_restart"),
            ],
        ]
        if has_online or has_uncertain:
            buttons.append([
                InlineKeyboardButton("🤖 Online Dersler Hakkında Konuş", callback_data="onboard_chat_online"),
            ])
        buttons.append([
            InlineKeyboardButton("Devam et (Düzenleme /courses'da)", callback_data="onboard_confirm_all"),
        ])

        await chat.send_message(
            text=text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown",
        )

        return OnboardingState.CONFIRM_COURSES

    except Exception as e:
        log.error("bot.schedule_parse_failed", error=str(e), exc_info=True)
        try:
            await processing_msg.delete()
        except Exception:
            pass

        await chat.send_message(
            f"❌ Ders programı analiz edilirken bir hata oluştu.\n"
            f"Tekrar dene veya /cancel ile iptal et.\n\n"
            f"Hata: {escape_dynamic_text(str(e)[:200], parse_mode='Markdown')}",
            parse_mode="Markdown",
        )
        _init_buffers(context)
        return OnboardingState.ASK_SCHEDULE_PHOTO


async def handle_onboard_confirm_all(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Tüm dersleri onayla ve kurulumu tamamla."""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    courses = context.user_data.get("parsed_courses", [])
    course_count = len(courses)

    # Aynı butona iki kez basılırsa duplicate insert olmasın (idempotency guard)
    if context.user_data.get("saving_courses"):
        await query.answer("⏳ Zaten kaydediliyor...", show_alert=False)
        return ConversationHandler.END
    context.user_data["saving_courses"] = True

    if courses:
        from src.db.connection import get_session
        from src.db.repositories.course import CourseRepository
        from src.db.repositories.user import UserRepository
        from src.scheduler.lesson_scheduler import schedule_all_courses_for_user

        try:
            # 1) DB'ye kaydet (DB hatalarını ayrı yakala)
            try:
                async with get_session() as session:
                    # 1. Kullanıcının veritabanında olduğundan emin ol
                    user_repo = UserRepository(session)
                    user = await user_repo.get_by_id(user_id)
                    if not user:
                        await user_repo.create_or_update(
                            user_id=user_id,
                            first_name=update.effective_user.first_name,
                            username=update.effective_user.username,
                        )
                        await session.commit()

                    # 2. Dersleri DB'ye kaydet
                    course_repo = CourseRepository(session)
                    # Onboarding yeni programı "source of truth" kabul eder: eski aktif dersleri pasife çek.
                    await course_repo.deactivate_all_for_user(user_id=user_id)
                    await course_repo.bulk_create_from_parsed(user_id=user_id, parsed_courses=courses)
                    await session.commit()
            except SQLAlchemyError as e:
                log.error("bot.onboard_db_failed", user_id=user_id, error=str(e), exc_info=True)
                await query.edit_message_text(
                    "❌ Dersler kaydedilirken bir veritabanı hatası oluştu. Lütfen yöneticinize başvurun."
                )
                return ConversationHandler.END

            # 2) Scheduler'a ekle (DB değil, zamanlama hatası olabilir)
            try:
                scheduled_jobs = await schedule_all_courses_for_user(user_id)
                log.info("bot.onboard_courses_scheduled", user_id=user_id, count=len(scheduled_jobs))
            except Exception as e:
                log.error("bot.onboard_scheduler_failed", user_id=user_id, error=str(e), exc_info=True)
                await query.edit_message_text(
                    "⚠️ Dersler veritabanına kaydedildi ancak zamanlanırken bir hata oluştu.\n"
                    "Lütfen birkaç dakika sonra `/status` ile kontrol edin veya yöneticinize başvurun."
                )
                return ConversationHandler.END
        finally:
            context.user_data.pop("saving_courses", None)

    # Temizle
    for key in ("parsed_courses", "parse_warnings", "input_images", "input_texts", "chat_history"):
        context.user_data.pop(key, None)

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


# ── Chat Online (Onboarding) ──

async def handle_onboard_chat_online(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Online ders chatbot moduna gir (onboarding)."""
    query = update.callback_query
    await query.answer()

    courses = context.user_data.get("parsed_courses", [])
    online_courses = [c for c in courses if c.get("online_mi") is True or c.get("online_mi") is None]

    if not online_courses:
        await query.answer("Online veya belirsiz ders yok!", show_alert=True)
        return OnboardingState.CONFIRM_COURSES

    context.user_data["chat_history"] = []

    lines = ["🤖 **Online Ders Düzenleme Chatbot**\n"]
    lines.append("Online ve belirsiz dersler:\n")
    for i, c in enumerate(online_courses):
        status = "🟢 Online" if c.get("online_mi") is True else "❓ Belirsiz"
        safe_name = escape_dynamic_text(c["ders_adi"], parse_mode="Markdown")
        end_text = c.get("bitis_saati") or "?"
        lines.append(
            f"  {i+1}. **{safe_name}** — {c['gun']} {c['baslangic_saati']}–{end_text} [{status}]"
        )

    lines.append("\n💬 Bu dersler hakkında değişiklik yapmak için yazabilirsin.")
    lines.append("Örnek: _'Kariyer Planlama aslında Salı 14:00'te'_")
    lines.append("\nBitirince *tamam* yaz veya butona bas.")

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Tamam, Onay Ekranına Dön ✅", callback_data="onboard_chat_done")]
    ])

    await query.edit_message_text(
        text="\n".join(lines), reply_markup=keyboard, parse_mode="Markdown",
    )

    return OnboardingState.CHAT_ONLINE_COURSES


async def handle_onboard_chat_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Kullanıcının chatbot mesajını işle (onboarding)."""
    text = update.message.text.strip()

    if text.lower() in _DONE_KEYWORDS:
        return await _onboard_chat_done(update, context)

    # Import chatbot logic from schedule handler
    from src.bot.handlers.schedule import _chat_with_llm

    courses = context.user_data.get("parsed_courses", [])
    chat_history = context.user_data.get("chat_history", [])
    chat_history.append({"role": "user", "content": text})
    context.user_data["chat_history"] = chat_history

    processing_msg = await update.message.reply_text("💭 Düşünüyorum...")

    try:
        updated_courses, reply = await _chat_with_llm(courses, chat_history)

        if updated_courses:
            context.user_data["parsed_courses"] = updated_courses

        chat_history.append({"role": "assistant", "content": reply})
        context.user_data["chat_history"] = chat_history

        try:
            await processing_msg.delete()
        except Exception:
            pass

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("Tamam, Onay Ekranına Dön ✅", callback_data="onboard_chat_done")]
        ])

        await update.message.reply_text(
            f"🤖 {reply}", reply_markup=keyboard, parse_mode="Markdown",
        )

    except Exception as e:
        log.error("bot.onboard_chat_failed", error=str(e))
        try:
            await processing_msg.delete()
        except Exception:
            pass
        await update.message.reply_text(
            f"❌ Bir hata oluştu: {escape_dynamic_text(str(e)[:200], parse_mode='Markdown')}\nTekrar dene.",
            parse_mode="Markdown",
        )

    return OnboardingState.CHAT_ONLINE_COURSES


async def handle_onboard_chat_done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Chatbot'tan çıkış callback — onay ekranına dön."""
    query = update.callback_query
    await query.answer()
    return await _onboard_chat_done(update, context)


async def _onboard_chat_done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Chat modundan çık, onay ekranına dön."""
    courses = context.user_data.get("parsed_courses", [])
    context.user_data.pop("chat_history", None)

    from src.core.models import ParsedCourse, ScheduleParseResult
    from src.vision.schedule_parser import format_courses_for_telegram

    pc_list = [ParsedCourse(**c) for c in courses]
    result_obj = ScheduleParseResult(courses=pc_list, raw_text="", parse_warnings=[])
    result_text = format_courses_for_telegram(result_obj)

    has_online = any(c.get("online_mi") is True for c in courses)
    has_uncertain = any(c.get("online_mi") is None for c in courses)

    buttons = [
        [
            InlineKeyboardButton("Tümünü Onayla ✅", callback_data="onboard_confirm_all"),
            InlineKeyboardButton("Baştan Al 🔄", callback_data="onboard_restart"),
        ],
    ]
    if has_online or has_uncertain:
        buttons.append([
            InlineKeyboardButton("🤖 Online Dersler Hakkında Konuş", callback_data="onboard_chat_online"),
        ])

    chat = update.effective_chat
    await chat.send_message(
        text=result_text,
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode="Markdown",
    )
    return OnboardingState.CONFIRM_COURSES


async def handle_onboard_restart(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ders programı yüklemeyi baştan al."""
    query = update.callback_query
    await query.answer()

    for key in ("parsed_courses", "parse_warnings", "input_images", "input_texts", "chat_history"):
        context.user_data.pop(key, None)
    _init_buffers(context)

    await query.edit_message_text(
        "📷 Ders programının fotoğraflarını veya metin bilgisini gönder.\n"
        "Birden fazla fotoğraf/metin gönderebilirsin.\n"
        "Tamamlanınca *bitti* yaz.",
        parse_mode="Markdown",
    )
    return OnboardingState.ASK_SCHEDULE_PHOTO


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Onboarding'i iptal et."""
    for key in ("parsed_courses", "parse_warnings", "input_images", "input_texts", "chat_history"):
        context.user_data.pop(key, None)
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
                CallbackQueryHandler(handle_onboard_analyze, pattern="^onboard_analyze$"),
            ],
            OnboardingState.CONFIRM_COURSES: [
                CallbackQueryHandler(handle_onboard_confirm_all, pattern="^onboard_confirm_all$"),
                CallbackQueryHandler(handle_onboard_restart, pattern="^onboard_restart$"),
                CallbackQueryHandler(handle_onboard_chat_online, pattern="^onboard_chat_online$"),
            ],
            OnboardingState.CHAT_ONLINE_COURSES: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_onboard_chat_message),
                CallbackQueryHandler(handle_onboard_chat_done, pattern="^onboard_chat_done$"),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_command)],
        name="onboarding",
        persistent=True,
        allow_reentry=True,
        block=False,
    )
