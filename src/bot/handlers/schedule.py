"""
GhostAttend — Schedule Handler (Multi-Input + Chatbot)

Ders programı upload, Vision LLM parse, onay ve düzenleme akışları.
Birden fazla fotoğraf + metin girdisi desteği.
Online ders düzenleme için LLM chatbot entegrasyonu.
/courses, /schedule, /upload_schedule komutları.
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
from src.core.logging import get_logger
from src.bot.utils.safe_text import escape_dynamic_text
from src.vision.schedule_parser import format_courses_for_telegram, parse_schedule_images

log = get_logger(__name__)

# ── Ders Programı Upload Conversation States ──
WAITING_INPUT = 100
CONFIRM_COURSES = 101
EDIT_COURSE = 102
CHAT_ONLINE = 103

# ── Finish keywords ──
_DONE_KEYWORDS = {"bitti", "tamam", "done", "bitir", "gönder", "analiz et", "tamamdır"}


def _init_buffers(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Input buffer'larını başlat (yoksa)."""
    if "input_images" not in context.user_data:
        context.user_data["input_images"] = []  # list[(bytes, mime_type)]
    if "input_texts" not in context.user_data:
        context.user_data["input_texts"] = []  # list[str]


def _clear_buffers(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Input buffer'larını temizle."""
    context.user_data.pop("input_images", None)
    context.user_data.pop("input_texts", None)
    context.user_data.pop("parsed_courses", None)
    context.user_data.pop("parse_warnings", None)
    context.user_data.pop("chat_history", None)


# ── Multi-Input Handlers ──

async def _handle_photo_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Fotoğraf geldiğinde buffer'a ekle."""
    _init_buffers(context)

    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    image_bytes = await file.download_as_bytearray()

    context.user_data["input_images"].append((bytes(image_bytes), "image/jpeg"))

    count = len(context.user_data["input_images"])
    text_count = len(context.user_data.get("input_texts", []))

    status_parts = [f"📷 {count} fotoğraf"]
    if text_count:
        status_parts.append(f"📝 {text_count} metin")

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Analiz Et ✅", callback_data="schedule_analyze")]
    ])

    await update.message.reply_text(
        f"✅ Alındı! ({', '.join(status_parts)})\n\n"
        "Başka fotoğraf/metin gönderebilirsin.\n"
        "Tamamlanınca butona bas veya *bitti* yaz.",
        reply_markup=keyboard,
        parse_mode="Markdown",
    )
    return WAITING_INPUT


async def _handle_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Metin geldğinde: 'bitti' ise analiz başlat, değilse buffer'a ekle."""
    _init_buffers(context)

    text = update.message.text.strip()

    # "Bitti" benzeri komut mu?
    if text.lower() in _DONE_KEYWORDS:
        return await _start_analysis(update, context)

    # Metin buffer'a ekle
    context.user_data["input_texts"].append(text)

    count = len(context.user_data.get("input_images", []))
    text_count = len(context.user_data["input_texts"])

    status_parts = []
    if count:
        status_parts.append(f"📷 {count} fotoğraf")
    status_parts.append(f"📝 {text_count} metin")

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Analiz Et ✅", callback_data="schedule_analyze")]
    ])

    await update.message.reply_text(
        f"✅ Metin alındı! ({', '.join(status_parts)})\n\n"
        "Başka fotoğraf/metin gönderebilirsin.\n"
        "Tamamlanınca butona bas veya *bitti* yaz.",
        reply_markup=keyboard,
        parse_mode="Markdown",
    )
    return WAITING_INPUT


async def _handle_analyze_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """'Analiz Et' butonuna basıldığında analize başla."""
    query = update.callback_query
    await query.answer()
    return await _start_analysis(update, context, from_callback=True)


async def _start_analysis(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    from_callback: bool = False,
) -> int:
    """Buffer'daki tüm input'ları LLM'e gönder ve sonucu göster."""
    _init_buffers(context)

    images = context.user_data.get("input_images", [])
    texts = context.user_data.get("input_texts", [])

    if not images and not texts:
        msg = "📷 Henüz fotoğraf veya metin göndermedin. Lütfen ders programını paylaş."
        if from_callback:
            await update.callback_query.edit_message_text(msg)
        else:
            await update.message.reply_text(msg)
        return WAITING_INPUT

    # Yükleniyor mesajı
    chat = update.effective_chat
    processing_msg = await chat.send_message("🔍 Ders programı analiz ediliyor... ⏳")

    try:
        extra_text = "\n".join(texts) if texts else None

        # Sadece metin varsa (fotoğraf yok), metin-only parse
        if not images and extra_text:
            from src.vision.schedule_parser import parse_schedule_image
            # Metin girdisi için boş bir "görsel" yerine doğrudan text-based parse
            # Text-only modda dummy görsel gerekmiyor, extra_text ile multi-parse kullan
            result = await parse_schedule_images(
                images=[],
                extra_text=extra_text,
            )
        else:
            result = await parse_schedule_images(
                images=images,
                extra_text=extra_text,
            )

        # Sonuçları context'e kaydet
        context.user_data["parsed_courses"] = [c.model_dump() for c in result.courses]
        context.user_data["parse_warnings"] = result.parse_warnings

        # Buffer'ları temizle (artık gerekli değil)
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
            return WAITING_INPUT

        # Online durumu belirsiz ders var mı?
        has_uncertain = any(c.online_mi is None for c in result.courses)
        has_online = any(c.online_mi is True for c in result.courses)

        # Sonuçları göster
        text = format_courses_for_telegram(result)

        buttons = [
            [
                InlineKeyboardButton("Tümünü Onayla ✅", callback_data="courses_confirm_all"),
                InlineKeyboardButton("Düzenle ✏️", callback_data="courses_edit"),
            ],
            [InlineKeyboardButton("Baştan Al 🔄", callback_data="courses_restart")],
        ]

        # Online dersler veya belirsiz durumlar varsa chatbot butonu ekle
        if has_online or has_uncertain:
            buttons.insert(1, [
                InlineKeyboardButton("🤖 Online Dersler Hakkında Konuş", callback_data="courses_chat_online"),
            ])

        await chat.send_message(
            text=text,
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode="Markdown",
        )
        return CONFIRM_COURSES

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
        return WAITING_INPUT


# ── Confirm / Edit / Restart ──

async def _handle_confirm_all(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Tüm dersleri onayla ve kaydet."""
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
                    user_repo = UserRepository(session)
                    user = await user_repo.get_by_id(user_id)
                    if not user:
                        await user_repo.create_or_update(
                            user_id=user_id,
                            first_name=update.effective_user.first_name,
                            username=update.effective_user.username,
                        )
                        await session.commit()

                    course_repo = CourseRepository(session)
                    # Yeni yüklenen programı "source of truth" kabul et: eski aktif dersleri pasife çek.
                    await course_repo.deactivate_all_for_user(user_id=user_id)
                    await course_repo.bulk_create_from_parsed(user_id=user_id, parsed_courses=courses)
                    await session.commit()
            except SQLAlchemyError as e:
                log.error("bot.schedule_db_failed", user_id=user_id, error=str(e), exc_info=True)
                await query.edit_message_text(
                    "❌ Dersler kaydedilirken bir veritabanı hatası oluştu. Lütfen yöneticinize başvurun."
                )
                return ConversationHandler.END

            # 2) Scheduler'a ekle (DB değil, zamanlama hatası olabilir)
            try:
                scheduled_jobs = await schedule_all_courses_for_user(user_id)
                log.info("bot.schedule_courses_scheduled", user_id=user_id, count=len(scheduled_jobs))
            except Exception as e:
                log.error("bot.schedule_scheduler_failed", user_id=user_id, error=str(e), exc_info=True)
                await query.edit_message_text(
                    "⚠️ Dersler veritabanına kaydedildi ancak zamanlanırken bir hata oluştu.\n"
                    "Lütfen birkaç dakika sonra `/status` ile kontrol edin veya yöneticinize başvurun."
                )
                return ConversationHandler.END
        finally:
            context.user_data.pop("saving_courses", None)

    _clear_buffers(context)

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
            safe_course_name = escape_dynamic_text(course["ders_adi"], parse_mode="Markdown")
            safe_instructor = escape_dynamic_text(course.get("ogretim_uyesi", "Belirtilmemiş") or "Belirtilmemiş", parse_mode="Markdown")

            # Online status badge
            if course.get("online_mi") is True:
                online_text = "🟢 Online"
            elif course.get("online_mi") is False:
                online_text = "🔴 Yüz yüze"
            else:
                online_text = "❓ Belirsiz"

            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("Sil 🗑️", callback_data=f"delete_course_{idx}"),
                    InlineKeyboardButton("Online ✅", callback_data=f"set_online_{idx}"),
                    InlineKeyboardButton("Yüz yüze ❌", callback_data=f"set_offline_{idx}"),
                ],
                [InlineKeyboardButton("⬅️ Geri", callback_data="courses_edit")],
            ])

            end_text = course.get("bitis_saati") or "?"

            await query.edit_message_text(
                text=(
                    f"📖 **{safe_course_name}**\n\n"
                    f"📅 {course['gun']} {course['baslangic_saati']}–{end_text}\n"
                    f"👨‍🏫 {safe_instructor}\n"
                    f"🖥️ {course.get('platform', 'unknown').upper()}\n"
                    f"🎯 {online_text}"
                ),
                reply_markup=keyboard,
                parse_mode="Markdown",
            )

    elif data.startswith("delete_course_"):
        idx = int(data.split("_")[-1])
        if 0 <= idx < len(courses):
            deleted = courses.pop(idx)
            context.user_data["parsed_courses"] = courses
            safe_deleted = escape_dynamic_text(deleted["ders_adi"], parse_mode="Markdown")
            await query.edit_message_text(
                text=f"🗑️ **{safe_deleted}** silindi.",
                parse_mode="Markdown",
            )
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
        from src.core.models import ParsedCourse, ScheduleParseResult

        pc_list = [ParsedCourse(**c) for c in courses]
        result_obj = ScheduleParseResult(courses=pc_list, raw_text="", parse_warnings=[])
        result_text = format_courses_for_telegram(result_obj)

        has_online = any(c.get("online_mi") is True for c in courses)
        has_uncertain = any(c.get("online_mi") is None for c in courses)

        buttons = [
            [
                InlineKeyboardButton("Tümünü Onayla ✅", callback_data="courses_confirm_all"),
                InlineKeyboardButton("Düzenle ✏️", callback_data="courses_edit"),
            ],
            [InlineKeyboardButton("Baştan Al 🔄", callback_data="courses_restart")],
        ]
        if has_online or has_uncertain:
            buttons.insert(1, [
                InlineKeyboardButton("🤖 Online Dersler Hakkında Konuş", callback_data="courses_chat_online"),
            ])

        await query.edit_message_text(
            text=result_text,
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode="Markdown",
        )
        return CONFIRM_COURSES

    return EDIT_COURSE


async def _handle_restart(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Baştan al — yeni fotoğraf/metin iste."""
    query = update.callback_query
    await query.answer()

    _clear_buffers(context)
    _init_buffers(context)

    await query.edit_message_text(
        "📷 Ders programının fotoğraflarını veya metin bilgisini gönder.\n"
        "Birden fazla fotoğraf/metin gönderebilirsin.\n"
        "Tamamlanınca *bitti* yaz.",
        parse_mode="Markdown",
    )

    return WAITING_INPUT


# ── LLM Chatbot for Online Course Editing ──

async def _handle_chat_online_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Online ders chatbot moduna gir."""
    query = update.callback_query
    await query.answer()

    courses = context.user_data.get("parsed_courses", [])
    online_courses = [c for c in courses if c.get("online_mi") is True or c.get("online_mi") is None]

    if not online_courses:
        await query.answer("Online veya belirsiz ders yok!", show_alert=True)
        return CONFIRM_COURSES

    # Chat history başlat
    context.user_data["chat_history"] = []

    lines = ["🤖 **Online Ders Düzenleme Chatbot**\n"]
    lines.append("Online ve belirsiz dersler:\n")
    for i, c in enumerate(online_courses):
        status = "🟢 Online" if c.get("online_mi") is True else "❓ Belirsiz"
        end_text = c.get("bitis_saati") or "?"
        lines.append(
            f"  {i+1}. **{c['ders_adi']}** — {c['gun']} {c['baslangic_saati']}–{end_text} [{status}]"
        )

    lines.append("\n💬 Bu dersler hakkında değişiklik yapmak için yazabilirsin.")
    lines.append("Örnek: _'Kariyer Planlama aslında Salı 14:00'te'_")
    lines.append("Örnek: _'İngilizce dersi yüz yüze, online değil'_")
    lines.append("\nBitirince *tamam* yaz veya butona bas.")

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Tamam, Onay Ekranına Dön ✅", callback_data="chat_done")]
    ])

    await query.edit_message_text(
        text="\n".join(lines),
        reply_markup=keyboard,
        parse_mode="Markdown",
    )

    return CHAT_ONLINE


async def _handle_chat_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Kullanıcının chatbot mesajını LLM ile işle."""
    text = update.message.text.strip()

    if text.lower() in _DONE_KEYWORDS:
        return await _chat_done_and_return(update, context)

    courses = context.user_data.get("parsed_courses", [])
    chat_history = context.user_data.get("chat_history", [])

    # LLM'e gönderilecek context
    chat_history.append({"role": "user", "content": text})
    context.user_data["chat_history"] = chat_history

    processing_msg = await update.message.reply_text("💭 Düşünüyorum...")

    try:
        updated_courses, reply = await _chat_with_llm(courses, chat_history)

        # Güncelleme yapıldıysa kaydet
        if updated_courses:
            context.user_data["parsed_courses"] = updated_courses

        chat_history.append({"role": "assistant", "content": reply})
        context.user_data["chat_history"] = chat_history

        try:
            await processing_msg.delete()
        except Exception:
            pass

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("Tamam, Onay Ekranına Dön ✅", callback_data="chat_done")]
        ])

        await update.message.reply_text(
            f"🤖 {reply}",
            reply_markup=keyboard,
            parse_mode="Markdown",
        )

    except Exception as e:
        log.error("bot.chat_llm_failed", error=str(e), exc_info=True)
        try:
            await processing_msg.delete()
        except Exception:
            pass
        await update.message.reply_text(
            f"❌ Bir hata oluştu: {escape_dynamic_text(str(e)[:200], parse_mode='Markdown')}\nTekrar dene.",
            parse_mode="Markdown",
        )

    return CHAT_ONLINE


async def _chat_with_llm(
    courses: list[dict],
    chat_history: list[dict],
) -> tuple[list[dict] | None, str]:
    """
    LLM ile konuşarak ders listesini güncelle.
    Returns: (updated_courses or None, reply_text)
    """
    import json
    from src.core.config import settings
    from src.vision.prompts import SCHEDULE_PARSE_PROMPT  # noqa: F811

    courses_json = json.dumps(courses, ensure_ascii=False, indent=2)

    system_prompt = f"""Sen bir üniversite ders programı asistanısın. 
Kullanıcının mevcut ders listesi:

```json
{courses_json}
```

GÖREV:
1. Kullanıcı dersler hakkında değişiklik istediğinde, güncellenmiş ders listesini döndür.
2. Yanıtını ŞU FORMATTA ver:

Eğer güncelleme yapıyorsan:
```json
{{"action": "update", "courses": [...güncellenmiş tüm ders listesi...], "message": "Kısa açıklama"}}
```

Eğer sadece bilgi/sohbet ise:
```json
{{"action": "info", "message": "Yanıtın"}}
```

KURALLAR:
- Gün adları Türkçe olmalı: Pazartesi, Salı, Çarşamba, Perşembe, Cuma, Cumartesi, Pazar
- Saat formatı: HH:MM
- online_mi: true, false veya null
- platform: teams, zoom, meet veya unknown
- Sadece JSON döndür, başka metin ekleme.
"""

    provider = settings.AGENT_LLM_PROVIDER

    # Son kullanıcı mesajı
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(chat_history)

    if provider == "google":
        import google.generativeai as genai

        genai.configure(api_key=settings.GOOGLE_API_KEY)
        model = genai.GenerativeModel(settings.AGENT_LLM_MODEL)

        # Gemini'de system prompt + history'yi birleştir
        combined_text = system_prompt + "\n\n"
        for msg in chat_history:
            role = "Kullanıcı" if msg["role"] == "user" else "Asistan"
            combined_text += f"{role}: {msg['content']}\n"

        response = await model.generate_content_async(
            combined_text,
            generation_config=genai.GenerationConfig(temperature=0.3, max_output_tokens=4096),
        )
        raw = response.text

    elif provider == "openai":
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        response = await client.chat.completions.create(
            model=settings.AGENT_LLM_MODEL,
            messages=messages,
            temperature=0.3,
            max_tokens=4096,
        )
        raw = response.choices[0].message.content or ""

    elif provider == "anthropic":
        import anthropic

        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        response = await client.messages.create(
            model=settings.AGENT_LLM_MODEL,
            max_tokens=4096,
            system=system_prompt,
            messages=[m for m in chat_history if m["role"] in ("user", "assistant")],
        )
        raw = response.content[0].text
    else:
        return None, "Desteklenmeyen LLM provider."

    # JSON parse
    from src.vision.schedule_parser import _extract_json_block

    try:
        json_str = _extract_json_block(raw)
        data = json.loads(json_str)

        action = data.get("action", "info")
        message = data.get("message", "İşlem tamamlandı.")

        if action == "update" and "courses" in data:
            return data["courses"], message
        else:
            return None, message

    except Exception:
        # JSON parse edilemezse ham yanıtı göster
        return None, raw[:500]


async def _handle_chat_done_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Chatbot'tan çıkış — onay ekranına dön."""
    query = update.callback_query
    await query.answer()
    return await _chat_done_and_return(update, context, from_callback=True)


async def _chat_done_and_return(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    from_callback: bool = False,
) -> int:
    """Chat modundan çık, onay ekranına dön."""
    courses = context.user_data.get("parsed_courses", [])
    context.user_data.pop("chat_history", None)

    from src.core.models import ParsedCourse, ScheduleParseResult

    pc_list = [ParsedCourse(**c) for c in courses]
    result_obj = ScheduleParseResult(courses=pc_list, raw_text="", parse_warnings=[])
    result_text = format_courses_for_telegram(result_obj)

    has_online = any(c.get("online_mi") is True for c in courses)
    has_uncertain = any(c.get("online_mi") is None for c in courses)

    buttons = [
        [
            InlineKeyboardButton("Tümünü Onayla ✅", callback_data="courses_confirm_all"),
            InlineKeyboardButton("Düzenle ✏️", callback_data="courses_edit"),
        ],
        [InlineKeyboardButton("Baştan Al 🔄", callback_data="courses_restart")],
    ]
    if has_online or has_uncertain:
        buttons.insert(1, [
            InlineKeyboardButton("🤖 Online Dersler Hakkında Konuş", callback_data="courses_chat_online"),
        ])

    chat = update.effective_chat
    await chat.send_message(
        text=result_text,
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode="Markdown",
    )
    return CONFIRM_COURSES


async def _cancel_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ders programı yüklemeyi iptal et."""
    _clear_buffers(context)
    await update.message.reply_text("⏹️ Ders programı yükleme iptal edildi.")
    return ConversationHandler.END


def get_schedule_upload_handler() -> ConversationHandler:
    """Ders programı yükleme ConversationHandler'ı (multi-input + chatbot)."""

    async def _upload_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
        _init_buffers(context)
        await update.message.reply_text(
            "📷 Ders programının fotoğraflarını veya metin bilgisini gönder.\n"
            "Birden fazla fotoğraf ve/veya metin gönderebilirsin.\n"
            "Tamamlanınca *bitti* yaz veya butona bas.",
            parse_mode="Markdown",
        )
        return WAITING_INPUT

    return ConversationHandler(
        entry_points=[CommandHandler("upload_schedule", _upload_start)],
        states={
            WAITING_INPUT: [
                MessageHandler(filters.PHOTO, _handle_photo_input),
                MessageHandler(filters.TEXT & ~filters.COMMAND, _handle_text_input),
                CallbackQueryHandler(_handle_analyze_callback, pattern="^schedule_analyze$"),
            ],
            CONFIRM_COURSES: [
                CallbackQueryHandler(_handle_confirm_all, pattern="^courses_confirm_all$"),
                CallbackQueryHandler(_handle_edit, pattern="^courses_edit$"),
                CallbackQueryHandler(_handle_restart, pattern="^courses_restart$"),
                CallbackQueryHandler(_handle_chat_online_start, pattern="^courses_chat_online$"),
            ],
            EDIT_COURSE: [
                CallbackQueryHandler(
                    _handle_edit_course,
                    pattern="^(edit_course_|delete_course_|set_online_|set_offline_|add_course|courses_back)"
                ),
                CallbackQueryHandler(_handle_edit, pattern="^courses_edit$"),
            ],
            CHAT_ONLINE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, _handle_chat_message),
                CallbackQueryHandler(_handle_chat_done_callback, pattern="^chat_done$"),
            ],
        },
        fallbacks=[CommandHandler("cancel", _cancel_schedule)],
        name="schedule_upload",
        persistent=True,
        block=True,
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

    from src.core.constants import DAYS_TR

    day_names = {v: k for k, v in DAYS_TR.items()}

    lines = ["📚 **Kayıtlı Dersler**\n"]
    for i, c in enumerate(saved, 1):
        if c.is_online is True:
            online_badge = "🟢"
        elif c.is_online is False:
            online_badge = "🔴"
        else:
            online_badge = "❓"

        safe_name = escape_dynamic_text(c.name, parse_mode="Markdown")
        lines.append(
            f"{i}. {online_badge} **{safe_name}**\n"
            f"   {day_names.get(c.day_of_week, 'Bilinmeyen')} "
            f"{c.start_time.strftime('%H:%M')}–{c.end_time.strftime('%H:%M')}"
        )

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def schedule_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/schedule — Bugünün derslerini göster."""
    user = update.effective_user
    log.info("bot.schedule", user_id=user.id)

    from datetime import datetime
    from src.db.connection import get_session
    from src.db.repositories.course import CourseRepository

    today_num = datetime.now().weekday()

    async with get_session() as session:
        course_repo = CourseRepository(session)
        todays_courses = await course_repo.get_courses_for_day(user.id, today_num)

    if not todays_courses:
        await update.message.reply_text("📅 Bugün için planlanmış dersiniz bulunmuyor.")
        return

    lines = ["📅 **Bugünün Dersleri**\n"]
    for c in todays_courses:
        if c.is_online is True:
            badge = "🟢"
        elif c.is_online is False:
            badge = "🔴"
        else:
            badge = "❓"
        safe_name = escape_dynamic_text(c.name, parse_mode="Markdown")
        lines.append(f"⏰ {c.start_time.strftime('%H:%M')} — {badge} **{safe_name}**")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


def get_schedule_handlers() -> list:
    """Schedule ile ilgili tüm handler'ları döndür."""
    return [
        get_schedule_upload_handler(),
        CommandHandler("courses", courses_command),
        CommandHandler("schedule", schedule_command),
    ]
