"""
GhostAttend — Schedule Handler

Ders programı upload, Vision LLM parse, onay ve düzenleme akışları.
/courses ve /schedule komutları.
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
from src.vision.schedule_parser import format_courses_for_telegram, parse_schedule_image

log = get_logger(__name__)

# ── Ders Programı Upload Conversation States ──
WAITING_PHOTO = 100
CONFIRM_COURSES = 101
EDIT_COURSE = 102


async def _process_schedule_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ders programı fotoğrafını Vision LLM ile analiz et."""
    if not update.message or not update.message.photo:
        await update.message.reply_text("📷 Lütfen ders programının fotoğrafını gönder.")
        return WAITING_PHOTO

    # En yüksek çözünürlüklü fotoğrafı al
    photo = update.message.photo[-1]

    # Yükleniyor mesajı
    processing_msg = await update.message.reply_text(
        "🔍 Ders programı analiz ediliyor... ⏳"
    )

    try:
        # Fotoğrafı indir
        file = await context.bot.get_file(photo.file_id)
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
            return WAITING_PHOTO

        # Sonuçları göster
        text = format_courses_for_telegram(result)

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("Tümünü Onayla ✅", callback_data="courses_confirm_all"),
                InlineKeyboardButton("Düzenle ✏️", callback_data="courses_edit"),
            ],
            [
                InlineKeyboardButton("Baştan Al 🔄", callback_data="courses_restart"),
            ],
        ])

        await update.message.reply_text(
            text=text,
            reply_markup=keyboard,
            parse_mode="Markdown",
        )

        return CONFIRM_COURSES

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
        return WAITING_PHOTO


async def _handle_confirm_all(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Tüm dersleri onayla ve kaydet."""
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
                user_repo = UserRepository(session)
                user = await user_repo.get_by_id(user_id)
                if not user:
                    await user_repo.create_or_update(
                        user_id=user_id,
                        first_name=update.effective_user.first_name,
                        username=update.effective_user.username
                    )
                    await session.commit()

                course_repo = CourseRepository(session)
                await course_repo.bulk_create_from_parsed(user_id=user_id, parsed_courses=courses)
                await session.commit()

            scheduled_jobs = await schedule_all_courses_for_user(user_id)
            log.info("bot.schedule_courses_scheduled", user_id=user_id, count=len(scheduled_jobs))

        except Exception as e:
            log.error("bot.schedule_db_schedule_failed", user_id=user_id, error=str(e))
            await query.edit_message_text(
                "❌ Dersler kaydedilirken bir veritabanı hatası oluştu. Lütfen yöneticinize başvurun."
            )
            return ConversationHandler.END

    await query.edit_message_text(
        text=(
            f"🎉 Harika! **{course_count} ders** başarıyla veritabanına kaydedildi ve zamanlandı.\n\n"
            "Sistem her ders başlamadan 5 dakika önce otomatik olarak "
            "harekete geçecek. Derse girildiğinde sana bildirim göndereceğim.\n\n"
            "Yönetim komutları:\n"
            "/status — aktif oturumu ve zamanlanmış derslerini gör\n"
            "/cancel — aktif oturumu iptal et\n"
            "/courses — derslerini listele\n"
            "/reauth — kimlik doğrulamayı yenile"
        ),
        parse_mode="Markdown",
    )

    return ConversationHandler.END


async def _handle_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ders düzenleme moduna geç."""
    query = update.callback_query
    await query.answer()

    courses = context.user_data.get("parsed_courses", [])

    buttons = [
        [InlineKeyboardButton(f"✏️ {c['ders_adi']}", callback_data=f"edit_course_{i}")]
        for i, c in enumerate(courses)
    ]
    buttons.append([InlineKeyboardButton("Ders Ekle +", callback_data="add_course")])
    buttons.append([InlineKeyboardButton("⬅️ Geri", callback_data="courses_back")])

    await query.edit_message_text(
        text="Hangi dersi düzenlemek istiyorsun?",
        reply_markup=InlineKeyboardMarkup(buttons),
    )

    return EDIT_COURSE


async def _handle_edit_course(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Belirli bir dersi düzenle."""
    query = update.callback_query
    await query.answer()

    data = query.data
    courses = context.user_data.get("parsed_courses", [])

    if data.startswith("edit_course_"):
        idx = int(data.split("_")[-1])
        if 0 <= idx < len(courses):
            course = courses[idx]

            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("Sil 🗑️", callback_data=f"delete_course_{idx}"),
                    InlineKeyboardButton("Online ✅", callback_data=f"set_online_{idx}"),
                    InlineKeyboardButton("Yüz yüze ❌", callback_data=f"set_offline_{idx}"),
                ],
                [InlineKeyboardButton("⬅️ Geri", callback_data="courses_edit")],
            ])

            await query.edit_message_text(
                text=(
                    f"📖 **{course['ders_adi']}**\n\n"
                    f"📅 {course['gun']} {course['baslangic_saati']}–{course['bitis_saati']}\n"
                    f"👨‍🏫 {course.get('ogretim_uyesi', 'Belirtilmemiş')}\n"
                    f"🖥️ {course.get('platform', 'unknown').upper()}\n"
                    f"🎯 Online: {'Evet' if course.get('online_mi') else 'Hayır' if course.get('online_mi') is False else 'Belirsiz'}"
                ),
                reply_markup=keyboard,
                parse_mode="Markdown",
            )

    elif data.startswith("delete_course_"):
        idx = int(data.split("_")[-1])
        if 0 <= idx < len(courses):
            deleted = courses.pop(idx)
            context.user_data["parsed_courses"] = courses
            await query.edit_message_text(
                text=f"🗑️ **{deleted['ders_adi']}** silindi.",
                parse_mode="Markdown",
            )
            # Düzenleme listesine geri dön
            return await _handle_edit(update, context)

    elif data.startswith("set_online_"):
        idx = int(data.split("_")[-1])
        if 0 <= idx < len(courses):
            courses[idx]["online_mi"] = True
            context.user_data["parsed_courses"] = courses
            await query.answer("✅ Online olarak işaretlendi")
            return await _handle_edit(update, context)

    elif data.startswith("set_offline_"):
        idx = int(data.split("_")[-1])
        if 0 <= idx < len(courses):
            courses[idx]["online_mi"] = False
            context.user_data["parsed_courses"] = courses
            await query.answer("❌ Yüz yüze olarak işaretlendi")
            return await _handle_edit(update, context)

    elif data == "courses_back":
        # Onay ekranına geri dön
        result_text = format_courses_for_telegram(
            type("Result", (), {"courses": [type("C", (), c)() for c in courses], "parse_warnings": []})()
        )
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("Tümünü Onayla ✅", callback_data="courses_confirm_all"),
                InlineKeyboardButton("Düzenle ✏️", callback_data="courses_edit"),
            ],
            [InlineKeyboardButton("Baştan Al 🔄", callback_data="courses_restart")],
        ])
        await query.edit_message_text(text=result_text, reply_markup=keyboard, parse_mode="Markdown")
        return CONFIRM_COURSES

    return EDIT_COURSE


async def _handle_restart(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Baştan al — yeni fotoğraf iste."""
    query = update.callback_query
    await query.answer()

    context.user_data.pop("parsed_courses", None)
    context.user_data.pop("parse_warnings", None)

    await query.edit_message_text(
        "📷 Yeni ders programı fotoğrafını gönder."
    )

    return WAITING_PHOTO


async def _cancel_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ders programı yüklemeyi iptal et."""
    context.user_data.pop("parsed_courses", None)
    await update.message.reply_text("⏹️ Ders programı yükleme iptal edildi.")
    return ConversationHandler.END


def get_schedule_upload_handler() -> ConversationHandler:
    """Ders programı yükleme ConversationHandler'ı."""
    return ConversationHandler(
        entry_points=[CommandHandler("upload_schedule", lambda u, c: u.message.reply_text(
            "📷 Ders programının fotoğrafını gönder.\n"
            "Resim net ve okunaklı olsun."
        ) or WAITING_PHOTO)],
        states={
            WAITING_PHOTO: [
                MessageHandler(filters.PHOTO, _process_schedule_photo),
            ],
            CONFIRM_COURSES: [
                CallbackQueryHandler(_handle_confirm_all, pattern="^courses_confirm_all$"),
                CallbackQueryHandler(_handle_edit, pattern="^courses_edit$"),
                CallbackQueryHandler(_handle_restart, pattern="^courses_restart$"),
            ],
            EDIT_COURSE: [
                CallbackQueryHandler(_handle_edit_course, pattern="^(edit_course_|delete_course_|set_online_|set_offline_|add_course|courses_back)"),
                CallbackQueryHandler(_handle_edit, pattern="^courses_edit$"),
            ],
        },
        fallbacks=[CommandHandler("cancel", _cancel_schedule)],
        name="schedule_upload",
        persistent=False,
    )


# ── Basit Komutlar ──

async def courses_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/courses — Kayıtlı dersleri listele (DB'den)."""
    user = update.effective_user
    log.info("bot.courses", user_id=user.id)

    from src.db.connection import get_session
    from src.db.repositories.course import CourseRepository

    async with get_session() as session:
        course_repo = CourseRepository(session)
        saved = await course_repo.get_user_courses(user.id, active_only=True)

    if not saved:
        await update.message.reply_text(
            "📚 Henüz ders kaydedilmemiş.\n"
            "/upload\\_schedule ile ders programını yükle.",
            parse_mode="Markdown",
        )
        return

    from src.core.constants import DAYS_MAP
    
    # Reverse map dictionary for day names to match DB numbers
    day_names = {v: k for k, v in {
        "Pazartesi": 0, "Salı": 1, "Çarşamba": 2, "Perşembe": 3, 
        "Cuma": 4, "Cumartesi": 5, "Pazar": 6
    }.items()}

    lines = ["📚 **Kayıtlı Dersler**\n"]
    for i, c in enumerate(saved, 1):
        lines.append(
            f"{i}. ✅ **{c.name}**\n"
            f"   {day_names.get(c.day_of_week, 'Bilinmeyen')} {c.start_time.strftime('%H:%M')}–{c.end_time.strftime('%H:%M')}"
        )

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def schedule_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/schedule — Bugünün derslerini göster."""
    user = update.effective_user
    log.info("bot.schedule", user_id=user.id)

    from datetime import datetime
    from src.db.connection import get_session
    from src.db.repositories.course import CourseRepository

    # Pazartesi 0, Pazar 6
    today_num = datetime.now().weekday()

    async with get_session() as session:
        course_repo = CourseRepository(session)
        todays_courses = await course_repo.get_courses_for_day(user.id, today_num)

    if not todays_courses:
        await update.message.reply_text("📅 Bugün için planlanmış dersiniz bulunmuyor.")
        return

    lines = ["📅 **Bugünün Dersleri**\n"]
    for c in todays_courses:
        lines.append(f"⏰ {c.start_time.strftime('%H:%M')} — **{c.name}**")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


def get_schedule_handlers() -> list:
    """Schedule ile ilgili tüm handler'ları döndür."""
    return [
        get_schedule_upload_handler(),
        CommandHandler("courses", courses_command),
        CommandHandler("schedule", schedule_command),
    ]
