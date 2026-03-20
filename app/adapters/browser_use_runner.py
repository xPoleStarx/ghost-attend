from __future__ import annotations

import asyncio
import base64
import logging
import re
import time
from typing import Any
from app.adapters.browser_agent_holder import (
    dispose_cached_agent,
    get_cached_agent,
    pop_cached_agent,
    set_cached_agent,
)
from app.adapters.hitl_pending import (
    clear_pending_hitl,
    record_pending_hitl,
    take_synthetic_hints_if_orphan,
)
from app.adapters.browser_session_holder import get_session
from app.config.settings import Settings
from app.domain.schemas import BrowserRunResult, BrowserRunStatus
from app.run_control import (
    clear_stop,
    emit_progress,
    is_stop_requested,
    mark_browser_run_active,
    mark_browser_run_idle,
    wait_stop,
)

logger = logging.getLogger(__name__)

_PROGRESS_MIN_INTERVAL_S = 32.0
_PROGRESS_MAX_PER_RUN = 7
_PROGRESS_COMBINED_MAX_LEN = 900
_PROGRESS_MEMORY_MAX_LEN = 360
_PROGRESS_GOAL_MAX_LEN = 320
_USER_PREVIEW_MAX_LEN = 100
_GOAL_LINE_MAX_LEN = 130

_GOAL_PREFIX_STRIP = re.compile(
    r"^(?:(?:verdict|eval|evaluation\s+previous\s+goal|memory|next\s*goal|previous)\s*:\s*)+",
    re.IGNORECASE,
)

_REPLY_LANG_TAG = re.compile(r"^\s*\[reply-lang:\s*(tr|en)\]\s*\n?", re.IGNORECASE)


def parse_reply_lang_directive(task_text: str) -> tuple[str | None, str]:
    """İlk satır `[reply-lang:tr|en]` ise ayıkla (dış ajan Telegram dilini iletsin)."""
    m = _REPLY_LANG_TAG.match(task_text)
    if not m:
        return None, task_text
    return m.group(1).lower(), task_text[m.end() :].lstrip()


def infer_reply_language(text: str) -> str:
    """Kullanıcıya dönük metin dili — önce Türkçe harf / yaygın sözcükler."""
    raw = (text or "").strip()
    if not raw:
        return "en"
    if any(c in raw for c in "ıİşŞğĞüÜöÖçÇ"):
        return "tr"
    low = raw.lower()
    if any(
        p in low
        for p in (
            " için ",
            " şifre",
            " giriş",
            " hesab",
            " lütfen",
            " sitesine ",
            " yapın",
            " yap ",
            " nedir",
            " yardım",
            " merhaba",
            " kullanıcı",
            " buraya ",
            " devam ",
            " türkçe",
        )
    ):
        return "tr"
    return "en"


_LOGIN_FRAGMENTS = (
    "/login",
    "login.",
    "signin",
    "sign-in",
    "/auth",
    "/oauth",
    "/session",
    "/account/login",
    "/wp-login",
    "/giris",
    "giris.",
)

# Arayüz metinleri ("Öğrenci Girişi", "sign in" linki vb.) yanlışlıkla tetiklemesin diye
# yalnızca kimlik/OTP ima eden ifadeler — "giriş" tek başına kullanılmaz (substring: ...Girişi).
# "captcha" çıkarıldı: model planında geçmesi tüm otomasyonu kesiyordu; basit CAPTCHA çözümü iç ajanın işi.
# "credential" tek başına çıkarıldı: "don't have credentials" gibi cümleler yanlış HITL tetikliyordu.
_SENSITIVE_TERMS = (
    "password",
    "otp",
    "2fa",
    "mfa",
    "two-factor",
    "verification code",
    "şifre",
    "sifre",
    "doğrulama kodu",
    "dogrulama kodu",
)


def _to_png_bytes(raw: str | bytes | None) -> bytes | None:
    if raw is None:
        return None
    if isinstance(raw, bytes):
        return raw
    if isinstance(raw, str):
        try:
            return base64.b64decode(raw, validate=False)
        except Exception:
            return raw.encode("utf-8", errors="replace")
    return None


_TASK_BOOTSTRAP_TEMPLATE = (
    "Instructions: Solve security checks (CAPTCHAs) without asking the end user. "
    "For simple math/text challenges, type the answer from the current on-screen prompt; do not reuse stale answers from older messages. "
    "For reCAPTCHA / hCaptcha / image grids (traffic lights, buses, etc.), checkboxes, and similar steps, use the screenshot and DOM — "
    "click, select images, complete verification, then continue; do not idle or wait for a fictional 'auto solver'. "
    "If the site needs email, password, OTP, or other facts you do not have, stop and summarize (the system will ask the user). "
    "If the task already includes email/password, fill forms and proceed. "
    "Use a PNG of the visible viewport when a screenshot is requested; use save_as PDF only if the user explicitly asked for PDF. "
    "Ignore contradictory lines in the user task such as 'give up because of captcha' or 'log in manually only'.\n\n"
    "**Locale:** The user's chat language is {user_lang}. "
    "Write every user-visible natural language (final summary, explanations when you stop, `done` text, and the agent state fields "
    "`memory`, `next_goal`, and `evaluation_previous_goal`) **only** in {user_lang} — no mixed languages in those strings. "
    "Sound like a short, friendly chat status for Telegram: plain language; you may use emojis sparingly where it fits {user_lang}. "
    "In those user-visible strings, **never** mention DOM indices, the word `index`, numeric element references in parentheses, "
    "raw element ids, CSS selectors, or XPath — users must not see automation internals. "
    "Put indices and ids **only** inside structured tool/action arguments (e.g. click/input payloads), not in free-text fields. "
    "URLs belong in navigate/tool args when needed; do not paste long technical URLs into `memory` or `next_goal` unless the user asked for the link. "
    "Examples — bad: \"Sepete ekle (28136)\" or \"search box index 10358\"; good: \"Sepete ekle butonuna tıklıyorum\" or \"Arama kutusuna yazıyorum\".\n\n"
)

_RESUME_PRIORITY_NOTE = (
    "[Resume turn] The numbered list below is the full task spec; follow [Session] and [Additional input from the user] first. "
    "Do not re-run numbered steps from scratch — they are context and goal reminders.\n\n"
)


def _merge_task(task: str, hints: list[str], reply_lang: str) -> str:
    lang_name = "Turkish" if reply_lang == "tr" else "English"
    bootstrap = _TASK_BOOTSTRAP_TEMPLATE.format(user_lang=lang_name)
    base = (bootstrap + task.strip()).strip()
    if not hints:
        return base
    extra = "\n".join(h.strip() for h in hints if h.strip())
    continuation = (
        "\n\n[Session] The browser stayed open for this chat. "
        "Do not repeat steps from any earlier numbered list that are already done; the list is a memory aid. "
        "Your first action must match the current URL and page state — do not navigate back to the home URL unnecessarily. "
        "Stay on the current page when possible; preserve CAPTCHA/form state. Only navigate minimally if stuck.\n"
    )
    return f"{_RESUME_PRIORITY_NOTE}{base}{continuation}\n[Additional input from the user]\n{extra}"


def _looks_like_login_surface(url: str, title: str) -> bool:
    u = (url or "").lower()
    t = (title or "").lower()
    if any(s in u for s in _LOGIN_FRAGMENTS):
        return True
    if any(s in t for s in ("sign in", "log in", "login", "giriş", "oturum")):
        return True
    return False


def _login_dom_looks_unready(browser_state: Any) -> bool:
    """CDP ax_tree/iframe yarışında boş 'minimal' DOM veya henüz yüklenmemiş giriş sayfası."""
    ds = getattr(browser_state, "dom_state", None)
    if ds is None:
        return True
    sm = getattr(ds, "selector_map", None)
    if sm is None:
        return True
    try:
        n = len(sm)
    except TypeError:
        return True
    return n < _LOGIN_DOM_UNREADY_SELECTOR_THRESHOLD


# Giriş sayfasında kalıp yalnızca formu/ekranı incelemek — kimlik istemeden HITL kesilmesin.
# Giriş URL'si eşleşti ama CDP ax_tree hatası / geç yükleme yüzünden selector_map boş kalabiliyor;
# hemen HITL kesmek boş ekranda kullanıcıya düşürür — birkaç adım iç ajanın beklemesine izin ver.
_LOGIN_HITL_DOM_UNREADY_MAX_DEFERS = 3
_LOGIN_DOM_UNREADY_SELECTOR_THRESHOLD = 4

_LOGIN_HITL_SUPPRESS_PHRASES = (
    "do not attempt to log in",
    "don't attempt to log in",
    "do not log in yet",
    "don't log in yet",
    "without logging in",
    "do not log in,",
    "don't log in,",
    "just confirm you are at the login",
    "only confirm",
    "not attempt to log in",
    "giriş yapma",
    "henüz giriş",
    "giriş yapmayın",
    "giriş yapmadan",
    "şifre girmeden",
    "sadece doğrula",
    "sadece ekranı doğrula",
    "yalnızca doğrula",
)


def _task_suppresses_login_surface_hitl(full_task: str) -> bool:
    low = (full_task or "").lower()
    return any(p in low for p in _LOGIN_HITL_SUPPRESS_PHRASES)


_INLINE_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# Örn: password '...' veya şifre '...' — görevde kimlik zaten yazılıyken HITL ile kesmeyelim.
_INLINE_PASSWORD_QUOTED = re.compile(
    r"(?i)(password|şifre|sifre)\s*['\"]([^'\"]{2,})['\"]",
)
# user@mail.com / şifre veya user@mail.com / pass123
_INLINE_EMAIL_SLASH_PASSWORD = re.compile(
    r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\s*/\s*[^\s\n,;]+",
)


def _task_has_inline_credentials(full_task: str) -> bool:
    """Görev metninde e-posta + şifre (tırnaklı veya e-posta / şifre) varsa giriş HITL atlanır."""
    if not full_task or not _INLINE_EMAIL.search(full_task):
        return False
    if _INLINE_PASSWORD_QUOTED.search(full_task):
        return True
    return bool(_INLINE_EMAIL_SLASH_PASSWORD.search(full_task))


def _agent_suggests_sensitive(agent_output: Any) -> bool:
    if agent_output is None:
        return False
    cs = getattr(agent_output, "current_state", None)
    if cs is None:
        return False
    parts = [
        getattr(cs, "next_goal", None),
        getattr(cs, "evaluation_previous_goal", None),
        getattr(cs, "memory", None),
    ]
    blob = " ".join(str(p) for p in parts if p).lower()
    return any(k in blob for k in _SENSITIVE_TERMS)


def _agent_prioritizing_captcha(agent_output: Any, url: str, title: str) -> bool:
    """Giriş sayfasındayken CAPTCHA adımı — login HITL kesilmesin.

    str(agent_output) kullanılmaz: görev metnindeki 'captcha' kelimesi her adımda yanlış pozitif üretiyordu.
    Giriş sonrası sayfada memory'de eski 'captcha' geçebileceği için yalnızca login yüzeyinde aktif.
    """
    if agent_output is None:
        return False
    if not _looks_like_login_surface(url, title):
        return False
    cs = getattr(agent_output, "current_state", None)
    if cs is None:
        return False
    blob = " ".join(
        str(p)
        for p in (
            getattr(cs, "next_goal", None),
            getattr(cs, "memory", None),
            getattr(cs, "evaluation_previous_goal", None),
        )
        if p
    ).lower()
    if "captcha" in blob or "güvenlik kodu" in blob or "guvenlik kodu" in blob:
        return True
    if " + " in blob and ("=" in blob or "?" in blob):
        return True
    if "input the answer" in blob or "solve the captcha" in blob or "captcha field" in blob:
        return True
    if any(
        k in blob
        for k in (
            "recaptcha",
            "hcaptcha",
            "image challenge",
            "görsel doğrulama",
            "gorsel dogrulama",
            "ben robot",
            "robot değilim",
            "not a robot",
            "i'm not a robot",
            "cloudflare",
            "bot detection",
        )
    ):
        return True
    return False


def _hitl_question(
    url: str | None,
    title: str | None,
    reason: str,
    *,
    agent_context: str | None = None,
    reply_lang: str = "en",
) -> str:
    u = url or ("(unknown url)" if reply_lang == "en" else "(bilinmeyen url)")
    ti = title or ""
    ctx = (agent_context or "").strip()
    tr = reply_lang == "tr"
    if reason == "login_or_auth_surface":
        if tr:
            lines = [
                "Tarayıcı giriş veya kimlik doğrulama ekranında (kullanıcı adı / e-posta, şifre, OTP).",
                f"Adres: {u}",
            ]
            if ti:
                lines.append(f"Sayfa başlığı: {ti}")
            if ctx:
                lines.append("")
                lines.append(f"Özet: {ctx[:2000]}")
            lines.extend(
                [
                    "",
                    "Devam etmek için kurum e-postanı ve şifreni tek mesajda yaz; OTP/2FA kodu gerekiyorsa onu da ekle. "
                    "Görsel veya reCAPTCHA tarayıcı ajanı tarafından çözülür, burada paylaşman gerekmez. "
                    "Bu bilgiler yalnızca bu oturumda otomasyon için kullanılır; paylaşım riskinin farkında ol.",
                ]
            )
        else:
            lines = [
                "The browser is on a sign-in or identity screen (username / email, password, OTP).",
                f"URL: {u}",
            ]
            if ti:
                lines.append(f"Page title: {ti}")
            if ctx:
                lines.append("")
                lines.append(f"Summary: {ctx[:2000]}")
            lines.extend(
                [
                    "",
                    "Reply in one message with your work/school email and password; add OTP/2FA if needed. "
                    "Visual or reCAPTCHA challenges are handled by the browser agent — you do not paste them here. "
                    "These details are only used for this session; you accept the sharing risk.",
                ]
            )
        return "\n".join(lines)[:4090]
    if tr:
        head = (
            "Otomasyonun devam etmesi için senden bilgi gerekiyor.\n"
            f"(Teknik not: {reason})\nSayfa: {u}"
        )
        if ti:
            head += f"\nBaşlık: {ti}"
        if ctx:
            head += f"\n\nAjan notu: {ctx[:1500]}"
        head += "\n\nGerekirse kullanıcı adı, şifre, doğrulama kodu veya kısa talimatı tek mesajda yaz."
    else:
        head = (
            "I need something from you to continue.\n"
            f"(Technical note: {reason})\nPage: {u}"
        )
        if ti:
            head += f"\nTitle: {ti}"
        if ctx:
            head += f"\n\nAgent note: {ctx[:1500]}"
        head += "\n\nReply in one message with username, password, verification code, or short instructions if needed."
    return head


def _agent_context_blurb(agent_output: Any) -> str | None:
    cs = getattr(agent_output, "current_state", None) if agent_output else None
    if cs is None:
        return None
    parts = [getattr(cs, "next_goal", None), getattr(cs, "memory", None)]
    blob = "\n".join(str(p).strip() for p in parts if p)
    return blob[:2500] if blob else None


# thread_id başına: HITL bayrakları + her run_task turunda güncellenen görev metni (Agent önbellekte
# kaldığında callback closure'ının eski hints_list/full_task tutmaması için).
_run_ctx: dict[str, dict[str, Any]] = {}


def _user_task_preview_from_instruction(task: str) -> str:
    _, rest = parse_reply_lang_directive((task or "").strip())
    compact = " ".join(rest.split())
    if len(compact) <= _USER_PREVIEW_MAX_LEN:
        return compact
    return compact[: _USER_PREVIEW_MAX_LEN - 1].rstrip() + "…"


def _sanitize_next_goal_line(raw: str) -> str:
    s = " ".join((raw or "").replace("\n", " ").split())
    while True:
        m = _GOAL_PREFIX_STRIP.match(s)
        if not m:
            break
        s = s[m.end() :].strip()
    if len(s) > _GOAL_LINE_MAX_LEN:
        s = s[: _GOAL_LINE_MAX_LEN - 1].rstrip() + "…"
    return s


def _sanitize_agent_progress_field(raw: str, max_len: int) -> str:
    """memory / next_goal için: boşluk birleştir, verdict öneklerini at, kısalt."""
    s = " ".join((raw or "").replace("\n", " ").split())
    while True:
        m = _GOAL_PREFIX_STRIP.match(s)
        if not m:
            break
        s = s[m.end() :].strip()
    if len(s) > max_len:
        s = s[: max_len - 1].rstrip() + "…"
    return s


def _compose_agent_progress_message(agent_output: Any) -> str | None:
    """Betik sarmalayıcı yok: yalnızca iç ajanın memory + next_goal metni (locale kurallarına uygun yazılmalı)."""
    cs = getattr(agent_output, "current_state", None) if agent_output else None
    if cs is None:
        return None
    memory = _sanitize_agent_progress_field(
        str(getattr(cs, "memory", None) or ""),
        _PROGRESS_MEMORY_MAX_LEN,
    )
    next_goal = _sanitize_agent_progress_field(
        str(getattr(cs, "next_goal", None) or ""),
        _PROGRESS_GOAL_MAX_LEN,
    )
    if not memory and not next_goal:
        return None
    if memory and next_goal:
        ml, nl = memory.lower(), next_goal.lower()
        if nl in ml or ml in nl:
            text = memory if len(memory) >= len(next_goal) else next_goal
        else:
            text = f"{memory} — {next_goal}"
    else:
        text = memory or next_goal
    if len(text) > _PROGRESS_COMBINED_MAX_LEN:
        text = text[: _PROGRESS_COMBINED_MAX_LEN - 1].rstrip() + "…"
    return text


def _init_run_ctx(
    thread_id: str,
    hints_list: list[str],
    full_task: str,
    reply_lang: str,
) -> dict[str, Any]:
    tid = str(thread_id)
    ctx = {
        "stop": False,
        "shot": None,
        "url": None,
        "title": None,
        "reason": None,
        "agent_context": None,
        "hints_list": list(hints_list),
        "full_task": full_task,
        "reply_lang": reply_lang,
        "last_progress_ts": 0.0,
        "last_progress_sig": "",
        "progress_sent_count": 0,
        "login_surface_dom_defers": 0,
    }
    _run_ctx[tid] = ctx
    return ctx


def _run_ctx_for(thread_id: str) -> dict[str, Any]:
    return _run_ctx[str(thread_id)]


def _clear_run_ctx(thread_id: str) -> None:
    _run_ctx.pop(str(thread_id), None)


async def _maybe_emit_agent_progress_narration(
    tid: str,
    step: int,
    agent_output: Any,
) -> None:
    """Telegram'a yalnızca iç ajanın kendi anlatımı (memory/next_goal); betik 'çalışıyorum' metni yok."""
    if step < 1 or is_stop_requested(tid):
        return
    ctx = _run_ctx_for(tid)
    sent = int(ctx.get("progress_sent_count") or 0)
    if sent >= _PROGRESS_MAX_PER_RUN:
        return
    line = _compose_agent_progress_message(agent_output)
    if not line:
        return
    now = time.monotonic()
    last_ts = float(ctx.get("last_progress_ts") or 0.0)
    last_sig = str(ctx.get("last_progress_sig") or "")
    sig = line
    if (now - last_ts) < _PROGRESS_MIN_INTERVAL_S and sig == last_sig:
        return

    ctx["last_progress_ts"] = now
    ctx["last_progress_sig"] = sig
    ctx["progress_sent_count"] = sent + 1
    await emit_progress(tid, line[:4096])


class BrowserUseRunner:
    """browser-use Agent sarmalayıcı: adım callback + güvenli durdurma (HITL)."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _llm(self):
        from browser_use import ChatGoogle

        return ChatGoogle(model=self._settings.gemini_model, api_key=self._settings.google_api_key)

    async def run_task(
        self,
        task: str,
        hints: list[str] | None = None,
        *,
        thread_id: str = "default",
        reply_lang: str | None = None,
    ) -> BrowserRunResult:
        hints_list = list(hints or [])
        if hints_list:
            clear_pending_hitl(thread_id)
        else:
            syn = take_synthetic_hints_if_orphan(thread_id)
            if syn:
                hints_list = list(syn)
        combined_for_lang = "\n".join([task.strip()] + [h.strip() for h in hints_list if h.strip()])
        lang = (reply_lang or infer_reply_language(combined_for_lang)).lower()
        if lang not in ("tr", "en"):
            lang = "en"
        full_task = _merge_task(task, hints_list, lang)
        holder = _init_run_ctx(
            thread_id,
            hints_list,
            full_task,
            lang,
        )

        tid = str(thread_id)
        clear_stop(tid)
        await mark_browser_run_active(tid)

        async def on_step(browser_state: Any, agent_output: Any, step: int) -> None:
            ctx = _run_ctx_for(tid)
            url = getattr(browser_state, "url", "") or ""
            title = getattr(browser_state, "title", "") or ""
            ctx["url"] = url or ctx["url"]
            ctx["title"] = title or ctx["title"]
            png = _to_png_bytes(getattr(browser_state, "screenshot", None))
            if png:
                ctx["shot"] = png
            ft = str(ctx.get("full_task") or "")
            hl = ctx.get("hints_list") or []
            if not _looks_like_login_surface(url, title):
                ctx["login_surface_dom_defers"] = 0
            # Kullanıcıdan ek bilgi geldiyse (interrupt sonrası): giriş sayfasında tekrar durdurma —
            # aksi halde her tur login.aspx yüzünden kesiliyor, tarayıcı sıfırlanıyor, döngü oluşuyor.
            if not hl:
                if _agent_prioritizing_captcha(agent_output, url, title):
                    logger.info("HITL defer: captcha/güvenlik kodu adımı — iç ajanın çözmesine izin veriliyor")
                    return
                if _looks_like_login_surface(url, title):
                    if _task_suppresses_login_surface_hitl(ft):
                        logger.info(
                            "HITL defer: görev giriş yapmadan gözlem/doğrulama istiyor — login yüzeyi kesilmiyor"
                        )
                        return
                    if _task_has_inline_credentials(ft):
                        logger.info(
                            "HITL defer: görev metninde satır içi e-posta/şifre var — iç ajanın doldurmasına izin veriliyor"
                        )
                        return
                    if _login_dom_looks_unready(browser_state):
                        nd = int(ctx.get("login_surface_dom_defers") or 0)
                        if nd < _LOGIN_HITL_DOM_UNREADY_MAX_DEFERS:
                            ctx["login_surface_dom_defers"] = nd + 1
                            logger.info(
                                "HITL defer: giriş yüzeyi ama DOM henüz yetersiz (muhtemel CDP ax_tree / yükleme gecikmesi) "
                                "— erteleme %s/%s",
                                nd + 1,
                                _LOGIN_HITL_DOM_UNREADY_MAX_DEFERS,
                            )
                            return
                    ctx["reason"] = "login_or_auth_surface"
                    ctx["agent_context"] = _agent_context_blurb(agent_output)
                    ctx["stop"] = True
                    logger.info("HITL trigger: login/auth surface (url/title)")
                    return
                if _agent_suggests_sensitive(agent_output):
                    ctx["reason"] = "model_indicated_sensitive_step"
                    ctx["agent_context"] = _agent_context_blurb(agent_output)
                    ctx["stop"] = True
                    logger.info("HITL trigger: agent output suggests sensitive step")
            await _maybe_emit_agent_progress_narration(tid, step, agent_output)

        async def should_stop() -> bool:
            if is_stop_requested(tid):
                return True
            return bool(_run_ctx_for(tid)["stop"])

        from browser_use import Agent

        browser_session = await get_session(thread_id, self._settings)
        try:
            continuation = bool(hints_list)
            cached = get_cached_agent(thread_id)

            if continuation and cached is not None:
                agent = cached
                agent.add_new_task(full_task)
                logger.info(
                    "Aynı browser-use Agent ile devam (add_new_task) thread_id=%s — takip görevi, URL yeniden navigasyonu atlanır",
                    tid,
                )
            elif continuation and cached is None:
                logger.warning(
                    "HITL devamı bekleniyordu ancak önbellekte Agent yok; yeni Agent oluşturuluyor thread_id=%s",
                    tid,
                )
                agent = Agent(
                    task=full_task,
                    llm=self._llm(),
                    browser_session=browser_session,
                    register_new_step_callback=on_step,
                    register_should_stop_callback=should_stop,
                    step_timeout=self._settings.browser_step_timeout,
                )
                set_cached_agent(thread_id, agent)
            else:
                if cached is not None:
                    await dispose_cached_agent(thread_id)
                agent = Agent(
                    task=full_task,
                    llm=self._llm(),
                    browser_session=browser_session,
                    register_new_step_callback=on_step,
                    register_should_stop_callback=should_stop,
                    step_timeout=self._settings.browser_step_timeout,
                )
                set_cached_agent(thread_id, agent)

            run_task = asyncio.create_task(agent.run(max_steps=self._settings.browser_max_steps))
            stop_task = asyncio.create_task(wait_stop(tid))
            await asyncio.wait(
                {run_task, stop_task},
                return_when=asyncio.FIRST_COMPLETED,
            )

            if stop_task.done() and not stop_task.cancelled():
                run_task.cancel()
                try:
                    await run_task
                except asyncio.CancelledError:
                    pass
                except Exception:
                    logger.debug("browser-use run after cancel", exc_info=True)
                clear_stop(tid)
                clear_pending_hitl(thread_id)
                await dispose_cached_agent(thread_id)
                _clear_run_ctx(thread_id)
                cancelled = (
                    "Görev kullanıcı tarafından durduruldu."
                    if holder.get("reply_lang") == "tr"
                    else "The task was stopped by the user."
                )
                return BrowserRunResult(
                    status=BrowserRunStatus.CANCELLED,
                    summary=cancelled,
                    last_url=holder.get("url"),
                    screenshot_png=holder.get("shot"),
                )

            stop_task.cancel()
            try:
                await stop_task
            except asyncio.CancelledError:
                pass

            try:
                history = run_task.result()
            except Exception as e:
                logger.exception("browser-use run failed")
                clear_pending_hitl(thread_id)
                await dispose_cached_agent(thread_id)
                _clear_run_ctx(thread_id)
                return BrowserRunResult(
                    status=BrowserRunStatus.ERROR,
                    summary="Tarayıcı görevi sırasında hata oluştu.",
                    last_url=holder.get("url"),
                    screenshot_png=holder.get("shot"),
                    raw_error=str(e),
                )

            agent_state = getattr(agent, "state", None)
            agent_stopped = bool(getattr(agent_state, "stopped", False))
            user_or_external_stop = is_stop_requested(tid) or (
                agent_stopped and not holder["stop"]
            )

            if user_or_external_stop:
                clear_stop(tid)
                clear_pending_hitl(thread_id)
                await dispose_cached_agent(thread_id)
                _clear_run_ctx(thread_id)
                cancelled = (
                    "Görev kullanıcı tarafından durduruldu."
                    if holder.get("reply_lang") == "tr"
                    else "The task was stopped by the user."
                )
                return BrowserRunResult(
                    status=BrowserRunStatus.CANCELLED,
                    summary=cancelled,
                    last_url=holder.get("url"),
                    screenshot_png=holder.get("shot"),
                )

            if holder["stop"]:
                q = _hitl_question(
                    holder.get("url"),
                    holder.get("title"),
                    str(holder.get("reason")),
                    agent_context=holder.get("agent_context"),
                    reply_lang=str(holder.get("reply_lang") or "en"),
                )
                tail = None
                try:
                    tail = history.final_result()  # type: ignore[attr-defined]
                except Exception:
                    tail = None
                reason_raw = holder.get("reason")
                record_pending_hitl(
                    thread_id,
                    holder.get("url"),
                    str(reason_raw) if reason_raw is not None else None,
                )
                return BrowserRunResult(
                    status=BrowserRunStatus.NEEDS_HUMAN,
                    summary="",
                    last_url=holder.get("url"),
                    screenshot_png=holder.get("shot"),
                    question=q,
                    history_tail=str(tail) if tail is not None else None,
                    hitl_reason=str(reason_raw) if reason_raw is not None else None,
                )

            final_text: str | None = None
            try:
                final_text = history.final_result()  # type: ignore[attr-defined]
            except Exception:
                final_text = None
            done_msg = (
                "Görev tamamlandı." if holder.get("reply_lang") == "tr" else "Task completed."
            )
            summary = str(final_text).strip() if final_text else done_msg
            clear_pending_hitl(thread_id)
            pop_cached_agent(thread_id)
            _clear_run_ctx(thread_id)
            return BrowserRunResult(
                status=BrowserRunStatus.DONE,
                summary=summary,
                last_url=holder.get("url"),
                screenshot_png=holder.get("shot"),
            )
        finally:
            await mark_browser_run_idle(tid)
