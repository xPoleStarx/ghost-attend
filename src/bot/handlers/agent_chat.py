"""
GhostAttend — Agentic Chat Handler

Kurulumdan sonra kullanıcıların doğal dil ile sistemle konuşmasını sağlar.
LLM, tool-call benzeri JSON çıktısı üretir; bot bu tool'ları çalıştırır.
"""

from __future__ import annotations

import json
from datetime import time, datetime
import re
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import ContextTypes

from src.bot.utils.safe_text import escape_dynamic_text
from src.core.constants import DAYS_TR
from src.core.logging import get_logger

log = get_logger(__name__)


def _parse_time_hhmm(value: str) -> time:
    return time.fromisoformat(value.strip())


def _day_to_int(day_tr: str) -> int:
    day_tr = day_tr.strip()
    if day_tr not in DAYS_TR:
        raise ValueError(f"Geçersiz gün: {day_tr}")
    return DAYS_TR[day_tr]


def _compute_next_lesson(courses) -> object | None:
    """
    Kullanıcının aktif dersleri arasından şu andan itibaren en yakın dersi bul.
    Haftalık döngü (7 gün) üzerinden en küçük pozitif delta'yı seçer.
    """
    if not courses:
        return None

    # Ders programı ve scheduler Europe/Istanbul üzerinden çalışıyor.
    # Buradaki hesap da aynı timezone'a göre yapılmalı ki "en yakın ders" yanlış çıkmasın.
    now = datetime.now(ZoneInfo("Europe/Istanbul"))
    now_minutes = now.hour * 60 + now.minute
    today_idx = now.weekday()  # Pazartesi=0

    best_course = None
    best_delta = None

    for c in courses:
        # day_of_week: 0-6
        course_day = int(getattr(c, "day_of_week", 0))
        start: time = getattr(c, "start_time")
        course_minutes = start.hour * 60 + start.minute

        day_delta = (course_day - today_idx) % 7
        if day_delta == 0 and course_minutes <= now_minutes:
            day_delta = 7

        total_minutes = day_delta * 24 * 60 + (course_minutes - now_minutes)

        if best_delta is None or total_minutes < best_delta:
            best_delta = total_minutes
            best_course = c

    return best_course


def _detect_intent(text: str) -> str | None:
    """
    Basit Türkçe pattern'lerle niyet tespiti.

    Dönüş:
        - "ask_join_or_status"
        - "ambiguous_schedule_change"
        - None
    """
    lowered = text.lower()

    # Derse katılma isteği / durum sorgusu (emir veya soru kipinde)
    join_patterns = [
        r"\bderse\s+gir\b",
        r"\bderse\s+girecek\s+misin\b",
        r"\bderse\s+katıl\b",
        r"\bderse\s+katılacak\s+mısın\b",
        r"\bderse\s+girmen\s+gerekiyor\b",
        r"\bşimdi\s+derse\s+gir\b",
    ]
    if any(re.search(p, lowered) for p in join_patterns):
        return "ask_join_or_status"

    # Ders saatini güncelle ama ders adı yoksa → belirsiz saat değişikliği
    has_time = bool(re.search(r"\b([01]?\d|2[0-3])[:\.][0-5]\d\b", lowered))
    mentions_update = any(
        kw in lowered
        for kw in [
            "ders saatini güncelle",
            "başlangıç saatini",
            "saati güncelle",
            "saatini değiştir",
        ]
    )
    mentions_course_name = any(
        kw in lowered for kw in ["kariyer", "veri yapıları", "matematik", "dersi "]
    )
    if has_time and mentions_update and not mentions_course_name:
        return "ambiguous_schedule_change"

    return None


async def handle_agent_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Normal metin mesajlarını agent chat olarak ele al.
    / komutları ve ConversationHandler içi mesajlar bu handler'a düşmez.
    """
    user = update.effective_user
    if not user or not update.message or not update.message.text:
        return

    text_raw = update.message.text
    if not text_raw:
        return

    text = text_raw.strip()
    if not text:
        return

    from src.core.config import settings
    from src.db.connection import get_session
    from src.db.repositories.credential import CredentialRepository
    from src.db.repositories.course import CourseRepository
    from src.scheduler.lesson_scheduler import schedule_all_courses_for_user
    from src.vision.schedule_parser import _extract_json_block

    async with get_session() as session:
        cred_repo = CredentialRepository(session)
        dys_url = await cred_repo.get_dys_url_for_user(user.id)

        course_repo = CourseRepository(session)
        courses = await course_repo.get_user_courses(user.id, active_only=True)

        courses_payload = [
            {
                "id": str(c.id),
                "name": c.name,
                "day_of_week": c.day_of_week,
                "start_time": c.start_time.strftime("%H:%M"),
                "end_time": c.end_time.strftime("%H:%M"),
                "platform": c.platform,
                "direct_url": c.direct_url,
                "is_online": c.is_online,
                "is_active": c.is_active,
            }
            for c in courses
        ]

        intent = _detect_intent(text)

        # ── Intent: Ders saatini belirsiz güncelleme isteği ──
        if intent == "ambiguous_schedule_change":
            await update.message.reply_text(
                "Saatini değiştirmek istediğin dersin adını da yazar mısın?\n"
                "Örnek: \"Kariyer Planlama dersinin saatini 23:30 yap\""
            )
            return

        # ── Intent: Derse girme / durum sorgusu ──
        if intent == "ask_join_or_status":
            from src.db.repositories.session import SessionRepository

            session_repo = SessionRepository(session)
            active = await session_repo.get_active_session(user.id)

            if active:
                course = next((c for c in courses if c.id == active.course_id), None)
                if course:
                    safe_name = escape_dynamic_text(course.name, parse_mode="Markdown")
                    day_name = {v: k for k, v in DAYS_TR.items()}.get(
                        course.day_of_week, "?"
                    )
                    await update.message.reply_text(
                        "Şu anda zaten bir derse katılım oturumu çalışıyor.\n\n"
                        f"📚 **{safe_name}** — {day_name} "
                        f"{course.start_time.strftime('%H:%M')}-"
                        f"{course.end_time.strftime('%H:%M')}",
                        parse_mode="Markdown",
                    )
                    return

            next_course = _compute_next_lesson(courses) if courses else None
            if not next_course:
                await update.message.reply_text(
                    "Şu anda derste değilim ve yakın zamanda zamanlanmış bir ders de görünmüyor."
                )
                return

            safe_name = escape_dynamic_text(next_course.name, parse_mode="Markdown")
            day_name = {v: k for k, v in DAYS_TR.items()}.get(
                next_course.day_of_week, "?"
            )
            await update.message.reply_text(
                "Şu an derste değilim.\n\n"
                f"⏰ En yakın dersin **{safe_name}** — {day_name} "
                f"{next_course.start_time.strftime('%H:%M')}-"
                f"{next_course.end_time.strftime('%H:%M')}.\n\n"
                "Bu derse zamanı geldiğinde otomatik gireceğim. İstersen "
                "\"Kariyer Planlama dersine şimdi katıl\" gibi net bir cümleyle "
                "hangi derse hemen girmemi istediğini söyleyebilirsin.",
                parse_mode="Markdown",
            )
            return

        # Kullanıcıya hızlı geri bildirim (LLM tabanlı akışlar için)
        processing = await update.message.reply_text("💭 Anlıyorum, hemen bakıyorum...")

        tool_spec = {
            "tools": [
                {
                    "name": "list_courses",
                    "description": "Kayıtlı dersleri listeler.",
                    "args": {},
                },
                {
                    "name": "update_course_time",
                    "description": "Bir dersin gün/saatini değiştirir ve yeniden zamanlar.",
                    "args": {
                        "course_name_query": "string (örn: 'Kariyer')",
                        "day": "string (örn: 'Salı') opsiyonel",
                        "start_time": "string HH:MM opsiyonel",
                        "end_time": "string HH:MM opsiyonel",
                    },
                },
                {
                    "name": "add_course",
                    "description": "Yeni ders ekler ve yeniden zamanlar.",
                    "args": {
                        "name": "string",
                        "day": "string (Pazartesi..Pazar)",
                        "start_time": "string HH:MM",
                        "end_time": "string HH:MM",
                        "platform": "string opsiyonel (teams/zoom/meet/unknown)",
                        "direct_url": "string opsiyonel",
                    },
                },
                {
                    "name": "deactivate_course",
                    "description": "Bir dersi pasifleştirir (zamanlamadan çıkar) ve yeniden zamanlar.",
                    "args": {"course_name_query": "string"},
                },
                {
                    "name": "get_next_lesson",
                    "description": "Şu andan itibaren en yakın aktif dersi bulur ve özetler.",
                    "args": {},
                },
                {
                    "name": "get_today_lessons",
                    "description": "Bugünkü tüm aktif dersleri listeler.",
                    "args": {},
                },
                {
                    "name": "get_session_status",
                    "description": "Aktif veya en son agent oturumu hakkında bilgi verir.",
                    "args": {},
                },
                {
                    "name": "start_manual_session",
                    "description": "Seçilen ders için hemen şimdi derse katılım oturumu başlatır.",
                    "args": {
                        "course_name_query": "string (örn: 'Kariyer')",
                    },
                },
                {
                    "name": "cancel_active_session",
                    "description": "Varsa aktif derse katılım oturumunu iptal eder.",
                    "args": {},
                },
                {
                    "name": "help",
                    "description": "Kısa örneklerle yardım mesajı üretir.",
                    "args": {},
                },
            ]
        }

        system_prompt = f"""
Sen GhostAttend'in otonom asistanısın. Kullanıcı Telegram üzerinden doğal dilde, Türkçe olarak istek yazar.

ELİNDEKİ DURUM:
- user_id: {user.id}
- dys_url_var_mi: {"evet" if dys_url else "hayır"}
- kayıtlı_dersler (JSON): {json.dumps(courses_payload, ensure_ascii=False)}
- tool'lar (JSON): {json.dumps(tool_spec, ensure_ascii=False)}

 GÖREV:
 - Önce kullanıcının niyetini anlamaya çalış.
 - Emin olduğun durumlarda en uygun tool ile isteği gerçekleştir.
 - Emin olmadığın yerde asla tahmin yürütme; kısa ve net bir soru ile kullanıcıdan ek bilgi iste.

 ÖRNEK İSTEK → TOOL EŞLEŞMELERİ:
- "en yakın ders hangisi" → action=tool, tool="get_next_lesson"
- "bugün hangi derslerim var" → action=tool, tool="get_today_lessons"
- "şu an derste misin", "derste misin" → action=tool, tool="get_session_status"
- "derse girecek misin", "derse girer misin", "derse katılacak mısın" ama açıkça \"şimdi\" demiyorsa
  → action=tool, tool="get_session_status"
- "kariyer planlama dersini salı 22:22 yap" → action=tool, tool="update_course_time"
  args: {{"course_name_query": "Kariyer Planlama", "day": "Salı", "start_time": "22:22"}}
- "yeni ders ekle: Yapay Zeka, Perşembe 10:00-11:30" → action=tool, tool="add_course"
  args: {{"name": "Yapay Zeka", "day": "Perşembe", "start_time": "10:00", "end_time": "11:30"}}
- "Kariyer Planlama dersine şimdi katıl", "Kariyer Planlama dersine hemen gir"
  → action=tool, tool="start_manual_session"
  args: {{"course_name_query": "Kariyer Planlama"}}
- "derse katılmayı iptal et" → action=tool, tool="cancel_active_session"
- "derslerimi listele" → action=tool, tool="list_courses"

ÇIKTI FORMATı (SADECE GEÇERLİ JSON):
```json
{{
  "action": "tool" | "reply",
  "tool": "tool_adı (action=tool ise zorunlu)",
  "args": {{ ... }},
  "message": "kullanıcıya gönderilecek kısa mesaj"
}}
```

KURALLAR:
- Sadece JSON döndür, başka metin veya açıklama ekleme.
- Ders seçerken course_name_query ile en iyi eşleşeni seç. Birden fazla güçlü aday varsa en olası olanı seç ve message içinde ne yaptığını belirt. Emin değilsen, action="reply" ile kullanıcıdan hangi dersi kastettiğini sor.
- Ders saatini değiştirme isteğinde ders adı NET değilse (sadece \"ders\", \"dersim\" vb. diyorsa) asla update_course_time tool'unu çağırma; action="reply" ile kullanıcıdan ders adını iste.
- Kullanıcı \"{ders adı} dersine şimdi katıl\", \"hemen {ders adı} dersine gir\" gibi EMİR kipinde net bir istek yazıyorsa:
  - action="tool", tool="start_manual_session" kullan.
  - message alanında, seçilen ders adını ve saatlerini içeren kısa, samimi bir onay/metin üret (örnek: "Tamam, Kariyer Planlama dersi için hemen derse katılım oturumu başlatıyorum.").
- Saatler her zaman \"HH:MM\" formatında olmalı ve 24 saatlik zaman kullanılmalı.
"""

        raw = await _call_llm(settings.AGENT_LLM_PROVIDER, settings.AGENT_LLM_MODEL, system_prompt, text)
        try:
            payload = json.loads(_extract_json_block(raw))
        except Exception:
            payload = {"action": "reply", "message": raw[:500]}

        action = payload.get("action", "reply")
        message = payload.get("message", "Tamam.")

        if action != "tool":
            await _safe_delete(processing)
            await update.message.reply_text(message)
            return

        tool = payload.get("tool")
        args = payload.get("args") or {}

        # day_of_week (int) → Türkçe gün adı
        inv_days = {v: k for k, v in DAYS_TR.items()}

        try:
            if tool == "help":
                await _safe_delete(processing)
                await update.message.reply_text(
                    "Şunları yazabilirsin:\n"
                    "- \"Kariyer Planlama dersini Salı 14:00-15:30 yap\"\n"
                    "- \"Veri Yapıları dersini pasifleştir\"\n"
                    "- \"Yeni ders ekle: Yapay Zeka, Perşembe 10:00-11:30\"\n"
                    "- \"Derslerimi listele\""
                )
                return

            if tool == "list_courses":
                if not courses:
                    await _safe_delete(processing)
                    await update.message.reply_text("Henüz ders kaydın yok. /upload_schedule ile ekleyebilirsin.")
                    return
                lines = ["📚 Kayıtlı dersler:\n"]
                inv_days = {v: k for k, v in DAYS_TR.items()}
                for c in courses:
                    lines.append(
                        f"- **{escape_dynamic_text(c.name, parse_mode='Markdown')}**: "
                        f"{inv_days.get(c.day_of_week,'?')} {c.start_time.strftime('%H:%M')}-{c.end_time.strftime('%H:%M')}"
                    )
                await _safe_delete(processing)
                await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
                return

            if tool == "update_course_time":
                name_q = str(args.get("course_name_query", "")).strip()
                if not name_q:
                    raise ValueError("course_name_query gerekli")

                matches = await course_repo.find_by_name(user.id, name_q, active_only=True, limit=5)
                if not matches:
                    await _safe_delete(processing)
                    await update.message.reply_text(
                        f"❌ \"{escape_dynamic_text(name_q, parse_mode='Markdown')}\" ile eşleşen ders bulamadım. /courses ile kontrol edebilirsin.",
                        parse_mode="Markdown",
                    )
                    return

                target = matches[0]
                day = args.get("day")
                start_s = args.get("start_time")
                end_s = args.get("end_time")

                day_int = _day_to_int(day) if day else None
                start_t = _parse_time_hhmm(start_s) if start_s else None
                end_t = _parse_time_hhmm(end_s) if end_s else None

                await course_repo.update_schedule(
                    target.id,
                    day_of_week=day_int,
                    start_time=start_t,
                    end_time=end_t,
                )
                await session.commit()

                # Zamanlamayı yenile
                await schedule_all_courses_for_user(user.id)

                await _safe_delete(processing)
                await update.message.reply_text(message or "✅ Güncellendi ve yeniden zamanlandı.")
                return

            if tool == "add_course":
                name = str(args.get("name", "")).strip()
                day = str(args.get("day", "")).strip()
                start_s = str(args.get("start_time", "")).strip()
                end_s = str(args.get("end_time", "")).strip()
                platform = str(args.get("platform", "teams")).strip() or "teams"
                direct_url = args.get("direct_url")

                if not (name and day and start_s and end_s):
                    raise ValueError("name, day, start_time, end_time gerekli")

                await course_repo.create(
                    user_id=user.id,
                    name=name,
                    day_of_week=_day_to_int(day),
                    start_time=_parse_time_hhmm(start_s),
                    end_time=_parse_time_hhmm(end_s),
                    platform=platform,
                    direct_url=str(direct_url).strip() if direct_url else None,
                )
                await session.commit()
                await schedule_all_courses_for_user(user.id)

                await _safe_delete(processing)
                await update.message.reply_text(message or "✅ Ders eklendi ve zamanlandı.")
                return

            if tool == "deactivate_course":
                name_q = str(args.get("course_name_query", "")).strip()
                if not name_q:
                    raise ValueError("course_name_query gerekli")

                matches = await course_repo.find_by_name(user.id, name_q, active_only=True, limit=5)
                if not matches:
                    await _safe_delete(processing)
                    await update.message.reply_text("❌ Eşleşen ders bulamadım.")
                    return

                target = matches[0]
                await course_repo.set_active(target.id, False)
                await session.commit()
                await schedule_all_courses_for_user(user.id)

                await _safe_delete(processing)
                await update.message.reply_text(message or "✅ Ders pasifleştirildi ve zamanlama güncellendi.")
                return

            if tool == "get_next_lesson":
                if not courses:
                    await _safe_delete(processing)
                    await update.message.reply_text(
                        "📚 Kayıtlı dersin yok. /upload_schedule ile ders programını ekleyebilirsin."
                    )
                    return

                next_course = _compute_next_lesson(courses)
                if not next_course:
                    await _safe_delete(processing)
                    await update.message.reply_text("📚 Yaklaşan bir ders bulamadım.")
                    return

                safe_name = escape_dynamic_text(next_course.name, parse_mode="Markdown")
                day_name = inv_days.get(next_course.day_of_week, "?")
                text_out = (
                    f"⏰ En yakın dersin:\n\n"
                    f"📚 **{safe_name}**\n"
                    f"📅 {day_name} {next_course.start_time.strftime('%H:%M')}–{next_course.end_time.strftime('%H:%M')}"
                )
                await _safe_delete(processing)
                await update.message.reply_text(text_out, parse_mode="Markdown")
                return

            if tool == "get_today_lessons":
                today_idx = datetime.now().weekday()
                today_courses = [c for c in courses if c.day_of_week == today_idx]

                await _safe_delete(processing)
                if not today_courses:
                    await update.message.reply_text("📅 Bugün için zamanlanmış ders görünmüyor.")
                    return

                lines = ["📅 **Bugünkü Derslerin:**\n"]
                for c in today_courses:
                    safe_name = escape_dynamic_text(c.name, parse_mode="Markdown")
                    lines.append(
                        f"- **{safe_name}** {c.start_time.strftime('%H:%M')}–{c.end_time.strftime('%H:%M')}"
                    )
                await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
                return

            if tool == "get_session_status":
                from src.db.repositories.session import SessionRepository

                session_repo = SessionRepository(session)
                active = await session_repo.get_active_session(user.id)

                await _safe_delete(processing)

                if active:
                    course = next((c for c in courses if c.id == active.course_id), None)
                    if course:
                        safe_name = escape_dynamic_text(course.name, parse_mode="Markdown")
                        day_name = inv_days.get(course.day_of_week, "?")
                        base = (
                            f"🎓 Şu anda **{safe_name}** dersi için bir oturum {active.status} durumda.\n"
                            f"📅 {day_name} {course.start_time.strftime('%H:%M')}–{course.end_time.strftime('%H:%M')}"
                        )
                    else:
                        base = f"🎓 Şu anda bir ders oturumu {active.status} durumda."

                    await update.message.reply_text(base, parse_mode="Markdown")
                    return

                # Aktif oturum yoksa, en yakın dersi söyle
                next_course = _compute_next_lesson(courses) if courses else None

                if next_course:
                    safe_name = escape_dynamic_text(next_course.name, parse_mode="Markdown")
                    day_name = inv_days.get(next_course.day_of_week, "?")
                    text_out = (
                        "Şu anda derste değilim.\n\n"
                        f"⏰ En yakın dersin **{safe_name}** — "
                        f"{day_name} {next_course.start_time.strftime('%H:%M')}–{next_course.end_time.strftime('%H:%M')}."
                    )
                else:
                    text_out = "Şu anda derste değilim ve zamanlanmış ders de bulamıyorum."

                await update.message.reply_text(text_out, parse_mode="Markdown")
                return

            if tool == "start_manual_session":
                from src.scheduler.tasks import attend_lesson_task

                name_q = str(args.get("course_name_query", "")).strip()
                if not name_q:
                    raise ValueError("course_name_query gerekli")

                matches = await course_repo.find_by_name(
                    user.id, name_q, active_only=True, limit=5
                )
                if not matches:
                    await _safe_delete(processing)
                    await update.message.reply_text(
                        f"❌ \"{escape_dynamic_text(name_q, parse_mode='Markdown')}\" ile eşleşen ders bulamadım. /courses ile kontrol edebilirsin.",
                        parse_mode="Markdown",
                    )
                    return

                target = matches[0]

                if not dys_url and not target.direct_url:
                    await _safe_delete(processing)
                    await update.message.reply_text(
                        "❌ Bu ders için DYS adresi veya direkt canlı ders bağlantısı bulunamadı. "
                        "Önce /upload_schedule ile programı güncellediğinden emin ol."
                    )
                    return

                safe_name = escape_dynamic_text(target.name, parse_mode="Markdown")
                day_name = inv_days.get(target.day_of_week, "?")
                await _safe_delete(processing)
                await update.message.reply_text(
                    "Şöyle yapalım:\n\n"
                    f"📚 **{safe_name}**\n"
                    f"📅 {day_name} {target.start_time.strftime('%H:%M')}-"
                    f"{target.end_time.strftime('%H:%M')}\n\n"
                    "Bu derse *hemen şimdi* benim girmemi istiyorsan, kısaca "
                    "\"Evet, şimdi gir\" yazabilirsin. Vazgeçmek istersen de "
                    "\"Boşver\" demen yeterli.",
                    parse_mode="Markdown",
                )

                # Kullanıcıdan gelecek onay/red için context'e basit bir bayrak yaz
                context.user_data["pending_manual_join"] = {
                    "course_id": str(target.id),
                    "course_name": target.name,
                    "end_time": target.end_time.strftime("%H:%M"),
                    "direct_url": target.direct_url,
                    "dys_search_hint": getattr(target, "dys_search_hint", None),
                    "dys_url": dys_url or "",
                }

                return

            # Manual join için kullanıcıdan gelen \"Evet, şimdi gir\" / \"Boşver\" yanıtlarını yakala
            pending = context.user_data.get("pending_manual_join")
            lowered_text = text.lower()
            if pending and tool in (None, "", "reply"):
                if "evet" in lowered_text or "tamam" in lowered_text or "gir" in lowered_text:
                    attend_lesson_task.delay(
                        user_id=user.id,
                        course_id=pending["course_id"],
                        course_name=pending["course_name"],
                        dys_url=pending["dys_url"],
                        end_time=pending["end_time"],
                        direct_url=pending["direct_url"],
                        dys_search_hint=pending["dys_search_hint"],
                    )
                    context.user_data.pop("pending_manual_join", None)

                    await update.message.reply_text(
                        "Tamam, bu ders için hemen derse katılım oturumu başlatıyorum. "
                        "Birazdan ekran görüntüleriyle ne yaptığımı haber veririm. 🤖"
                    )
                    return

                if "boşver" in lowered_text or "iptal" in lowered_text or "vazgeç" in lowered_text:
                    context.user_data.pop("pending_manual_join", None)
                    await update.message.reply_text("Tamam, bu dersi şimdilik elle bırakıyorum. İstersen sonra tekrar söyleyebilirsin.")
                    return

                attend_lesson_task.delay(
                    user_id=user.id,
                    course_id=str(target.id),
                    course_name=target.name,
                    dys_url=dys_url or "",
                    end_time=target.end_time.strftime("%H:%M"),
                    direct_url=target.direct_url,
                    dys_search_hint=getattr(target, "dys_search_hint", None),
                )

                await _safe_delete(processing)
                await update.message.reply_text(
                    message
                    or "✅ Ders için derse katılım oturumu hemen başlatılıyor. Durumu ekran görüntüleriyle ileteceğim."
                )
                return

            if tool == "cancel_active_session":
                from src.core.session_cancel import cancel_user_session

                redis_client = context.bot_data.get("redis")
                result = await cancel_user_session(
                    user_id=user.id,
                    redis_client=redis_client,
                    db_session=session,
                )
                await session.commit()
                context.user_data.clear()

                await _safe_delete(processing)

                if (
                    result.get("cancel_flag_set")
                    or result.get("db_cancelled")
                    or result.get("redis_deleted", 0) > 0
                ):
                    await update.message.reply_text(
                        "⏹️ İptal alındı. Aktif oturum durduruluyor ve geçici veriler temizleniyor.\n"
                        "Tekrar başlamak için /start yazabilirsin."
                    )
                else:
                    await update.message.reply_text(
                        "⏹️ İptal alındı. Şu anda aktif bir oturum görünmüyor; yine de geçici verileri temizledim.\n"
                        "Tekrar başlamak için /start yazabilirsin."
                    )
                return

            await _safe_delete(processing)
            await update.message.reply_text("⚠️ Bu isteği şu an otomatik yapamıyorum. /help yazabilirsin.")

        except Exception as e:
            log.error("agent_chat.tool_failed", user_id=user.id, tool=str(tool), error=str(e), exc_info=True)
            await _safe_delete(processing)
            await update.message.reply_text(
                f"❌ İşlem başarısız: {escape_dynamic_text(str(e)[:200], parse_mode='Markdown')}",
                parse_mode="Markdown",
            )


async def _safe_delete(message) -> None:
    try:
        await message.delete()
    except Exception:
        pass


async def _call_llm(provider: str, model: str, system_prompt: str, user_text: str) -> str:
    """
    Basit LLM çağrısı: tool-call yerine JSON üretmesini ister.
    """
    if provider == "google":
        import google.generativeai as genai

        from src.core.config import settings

        genai.configure(api_key=settings.GOOGLE_API_KEY)
        m = genai.GenerativeModel(model)
        combined = system_prompt + "\n\nKullanıcı: " + user_text
        resp = await m.generate_content_async(
            combined,
            generation_config=genai.GenerationConfig(temperature=0.2, max_output_tokens=2048),
        )
        return resp.text or ""

    if provider == "openai":
        from openai import AsyncOpenAI

        from src.core.config import settings

        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        resp = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text},
            ],
            temperature=0.2,
            max_tokens=2048,
        )
        return resp.choices[0].message.content or ""

    if provider == "anthropic":
        import anthropic

        from src.core.config import settings

        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        resp = await client.messages.create(
            model=model,
            max_tokens=2048,
            system=system_prompt,
            messages=[{"role": "user", "content": user_text}],
        )
        return resp.content[0].text

    raise ValueError(f"Desteklenmeyen LLM provider: {provider}")

