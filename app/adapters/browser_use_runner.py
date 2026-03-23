from __future__ import annotations

import asyncio
import base64
import logging
import re
import time
from typing import Any
from urllib.parse import urlparse

from app.adapters.browser_agent_holder import (
    dispose_cached_agent,
    get_cached_agent,
    set_cached_agent,
)
from app.adapters.hitl_pending import (
    clear_pending_hitl,
    record_pending_hitl,
    take_synthetic_hints_if_orphan,
)
from app.adapters.browser_action_guard import attach_navigate_policy, build_navigate_policy_from_task
from app.adapters.ghost_browser_tools import build_ghost_guarded_tools
from app.adapters.browser_session_holder import (
    clear_thread_browser_continuity,
    get_session,
    get_thread_last_browser_url,
    record_thread_last_browser_url,
)
from app.config.settings import Settings
from app.domain.schemas import BrowserRunResult, BrowserRunStatus
from app.run_control import (
    clear_stop,
    drain_mid_run_corrections,
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

# Giriş yüzeyi dışında: şifre kelimesi tek başına (ör. hafızada "şifre girildi") HITL üretmesin.
_SENSITIVE_TERMS_STRICT = (
    "otp",
    "2fa",
    "mfa",
    "two-factor",
    "two factor",
    "verification code",
    "doğrulama kodu",
    "dogrulama kodu",
    "authenticator",
)

_URL_IN_TEXT = re.compile(r"https?://[^\s\]>\"')]+", re.IGNORECASE)


def extract_primary_http_url(task_text: str) -> str | None:
    """Görev metnindeki ilk http(s) URL (browser-use'un ilk navigate çıkarımı ile hizalı)."""
    m = _URL_IN_TEXT.search(task_text or "")
    if not m:
        return None
    return m.group(0).rstrip(".,);]\"")


def extract_all_http_urls(task_text: str) -> list[str]:
    """Görev + ipuçlarındaki tüm http(s) URL'leri (sıra korunur, yinelenenler elenir)."""
    seen: set[str] = set()
    out: list[str] = []
    for m in _URL_IN_TEXT.finditer(task_text or ""):
        u = m.group(0).rstrip(".,);]\"")
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def _authoritative_targets_block(urls: list[str]) -> str:
    if not urls:
        return ""
    lines = "\n".join(f"- {u}" for u in urls)
    return (
        "[Authoritative user targets — follow strictly]\n"
        "The user explicitly provided these URL(s) as entry points or goals:\n"
        f"{lines}\n\n"
        "Rules:\n"
        "1. Treat these URLs as correct unless the page shows a clear hard failure (e.g. HTTP error page, explicit not-found for that resource on the site).\n"
        "2. Readiness or load timeouts, blank-looking first paint, or missing thumbnails are NOT evidence that the URL is wrong — retry on the same URL "
        "(scroll, wait, reload in-tab) before abandoning it.\n"
        "3. Do not switch to site search or invent a different channel/page identity to replace these URLs unless the task explicitly asks you to search "
        "or the site clearly confirms this URL is invalid.\n"
        "4. Never navigate to a different YouTube @handle than the one(s) in these URLs unless the user task explicitly requires finding another channel.\n"
        "5. In browser-use, the tool actions `navigate`, `search`, and `evaluate` end the action list for that step — use exactly one of them per step "
        "without pairing with `wait` or `click` in the same step.\n\n"
    )


_AGENT_EXTEND_SYSTEM_MESSAGE = (
    "GhostMyShit (Shitty) reliability addendum:\n"
    "- The tool actions `navigate`, `search`, and `evaluate` terminate the multi-action queue for that step. "
    "Never output another action after them in the same step; use the next step for follow-up (e.g. wait or click).\n"
    "- When the user message lists explicit http(s) URLs, treat them as authoritative targets. "
    "A page readiness timeout or temporarily empty-looking DOM is not sufficient proof to abandon them for search or guessed alternate URLs.\n"
)


def _normalize_site_host(url: str) -> str | None:
    try:
        p = urlparse((url or "").strip())
        if not p.netloc:
            return None
        h = p.netloc.lower()
        if h.startswith("www."):
            h = h[4:]
        return h
    except Exception:
        return None


def sites_match_for_continuity(a: str | None, b: str | None) -> bool:
    """Aynı host (www. yok sayılır) — takip görevinde add_new_task kullanılıp kullanılmayacağı."""
    ha, hb = _normalize_site_host(a or ""), _normalize_site_host(b or "")
    if not ha or not hb:
        return False
    return ha == hb


def _should_followup_on_live_session(thread_id: str, task_instruction: str) -> bool:
    """Önbellekte Agent varken boş-hint turu: aynı site veya görevde URL yoksa mevcut sekmede devam."""
    task_url = extract_primary_http_url(task_instruction)
    last = get_thread_last_browser_url(thread_id)
    if task_url is None:
        return True
    if last is None:
        return True
    return sites_match_for_continuity(task_url, last)


def _credential_action_already_done_in_blob(blob: str) -> bool:
    """Örn. 'şifre … girildi' — giriş sonrası yükleniyor adımında yanlış HITL'i engelle."""
    b = blob.lower()
    credish = any(
        x in b
        for x in (
            "şifre",
            "sifre",
            "password",
            "kullanıcı adı",
            "kullanici adi",
            "username",
        )
    )
    if not credish:
        return False
    past_tr = (
        "girildi",
        "yazıldı",
        "dolduruldu",
        "gönderildi",
        "giriş yapıldı",
        "giris yapildi",
        "girdi",
        "tıklandı",
        "tiklandi",
    )
    past_en = ("entered", "typed", "filled", "submitted", "clicked")
    return any(p in b for p in past_tr) or any(p in b for p in past_en)


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
    user_blob = "\n".join([task.strip()] + [h.strip() for h in hints if h.strip()])
    authority = _authoritative_targets_block(extract_all_http_urls(user_blob))
    bootstrap = _TASK_BOOTSTRAP_TEMPLATE.format(user_lang=lang_name)
    base = (bootstrap + authority + task.strip()).strip()
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


# OBS vb.: "Kullanıcı adı: x, Şifre: y" — e-posta zorunlu değil.
_INLINE_USER_LABEL = re.compile(
    r"(?i)(kullanıcı\s*adı|kullanici\s*adi|username|user\s*name|user\s*id)\s*[:，,]\s*([^\s\n,;]{2,})",
)
_INLINE_PASS_LABEL = re.compile(
    r"(?i)(şifre|sifre|password)\s*[:，,]\s*([^\s\n,;]{2,})",
)


def _task_has_actionable_login_creds(full_task: str) -> bool:
    """Görevde doldurulabilir kimlik bilgisi var mı (tekrarlayan giriş hatası HITL için)."""
    t = full_task or ""
    if _task_has_inline_credentials(t):
        return True
    if _INLINE_PASSWORD_QUOTED.search(t) and (_INLINE_USER_LABEL.search(t) or _INLINE_EMAIL.search(t)):
        return True
    return bool(_INLINE_USER_LABEL.search(t) and _INLINE_PASS_LABEL.search(t))


def _collapse_ws_lower(s: str) -> str:
    return " ".join((s or "").lower().replace("\n", " ").split())


def _eval_memory_blob(agent_output: Any) -> str:
    """Kimlik hatası tespiti: plan (next_goal) hariç — yalnızca değerlendirme + hafıza."""
    cs = getattr(agent_output, "current_state", None)
    if cs is None:
        return ""
    ev = str(getattr(cs, "evaluation_previous_goal", None) or "")
    mem = str(getattr(cs, "memory", None) or "")
    return _collapse_ws_lower(f"{ev} {mem}")


def _auth_failure_class_from_agent_state(agent_output: Any) -> str | None:
    """Aynı site hatası üst üste gelince streak (OBS: kullanıcı adı/şifre yanlış)."""
    b = _eval_memory_blob(agent_output)
    if not b:
        return None
    if (
        "kullanıcı adı veya şifre yanlış" in b
        or "kullanici adi veya sifre yanlis" in b
        or (
            "username or password" in b
            and ("incorrect" in b or "wrong" in b or "invalid" in b)
        )
    ):
        return "invalid_credentials"
    if "incorrect password" in b or "wrong password" in b:
        return "invalid_credentials"
    if "invalid credentials" in b:
        return "invalid_credentials"
    return None


def _summary_asks_for_credentials(text: str) -> bool:
    """İç ajan done ile kullanıcıdan kimlik istediğinde (NEEDS_HUMAN kaçırıldıysa) pending HITL için."""
    b = _collapse_ws_lower(text or "")
    if not b:
        return False
    asks_tr = (
        "kullanıcı adı" in b and "şifre" in b,
        "kullanici adi" in b and "sifre" in b,
        "paylaşır mısınız" in b and ("şifre" in b or "sifre" in b),
        "ileti" in b and "şifre" in b,
    )
    asks_en = (
        "username" in b and "password" in b and ("provide" in b or "share" in b or "need" in b or "enter" in b),
        "password" in b and "need" in b,
    )
    return any(asks_tr) or any(asks_en)


def _agent_suggests_sensitive(agent_output: Any, url: str, title: str) -> bool:
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
    if _looks_like_login_surface(url, title):
        return any(k in blob for k in _SENSITIVE_TERMS)
    if _credential_action_already_done_in_blob(blob):
        return False
    return any(k in blob for k in _SENSITIVE_TERMS_STRICT)


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
    if reason == "repeated_auth_failure":
        if tr:
            lines = [
                "Aynı giriş bilgileriyle birkaç kez denedim; site sürekli kullanıcı adı veya şifrenin yanlış olduğunu söylüyor.",
                f"Sayfa: {u}",
            ]
            if ti:
                lines.append(f"Başlık: {ti}")
            if ctx:
                lines.append("")
                lines.append(f"Özet: {ctx[:1800]}")
            lines.extend(
                [
                    "",
                    "Küçük bir yazım farkı olabilir (nokta, büyük/küçük harf, özel karakter). "
                    "Lütfen kurumdaki tam kullanıcı adı ve şifreyi kontrol et; düzeltilmiş bilgiyi veya kısa bir talimatı tek mesajda yaz.",
                ]
            )
        else:
            lines = [
                "I tried logging in several times with the credentials in the task; the site keeps saying the username or password is wrong.",
                f"Page: {u}",
            ]
            if ti:
                lines.append(f"Title: {ti}")
            if ctx:
                lines.append("")
                lines.append(f"Summary: {ctx[:1800]}")
            lines.extend(
                [
                    "",
                    "A small detail may be wrong (punctuation, case, special characters). "
                    "Please verify your exact username and password, then reply in one message with corrected values or short instructions.",
                ]
            )
        return "\n".join(lines)[:4090]
    if reason == "user_mid_run_message":
        if tr:
            lines = [
                "Çalışırken gönderdiğin mesajı aldım; tarayıcı oturumunu koruyarak durdurdum.",
                f"Sayfa: {u}",
            ]
            if ti:
                lines.append(f"Başlık: {ti}")
            if ctx:
                lines.append("")
                lines.append(f"Senin mesajın:\n{ctx[:3000]}")
            lines.append("")
            lines.append("Devam için düzeltmeyi veya talimatı onayla; gerekirse güncellenmiş şifre/kullanıcı adını tek mesajda yaz.")
        else:
            lines = [
                "I received your message while working and paused with the browser session kept open.",
                f"Page: {u}",
            ]
            if ti:
                lines.append(f"Title: {ti}")
            if ctx:
                lines.append("")
                lines.append(f"Your message:\n{ctx[:3000]}")
            lines.append("")
            lines.append("Reply in one message to confirm or send corrected credentials / instructions to continue.")
        return "\n".join(lines)[:4090]
    if reason == "stuck_subgoal":
        if tr:
            lines = [
                "Aynı hedef üzerinde çok fazla tekrar oldu; sayfa durumu ilerlemedi. Tarayıcıyı güvenli şekilde durdurdum.",
                f"Sayfa: {u}",
            ]
            if ti:
                lines.append(f"Başlık: {ti}")
            if ctx:
                lines.append("")
                lines.append("Ne denendi / son durum (özet):")
                lines.append(ctx[:3200])
            lines.extend(
                [
                    "",
                    "Görevi netleştirmek veya farklı bir yol istiyorsan kısa yaz; oturum açık kaldıysa devam edebilirim.",
                ]
            )
        else:
            lines = [
                "The browser agent hit a repeated loop with no real progress on the same subgoal, so I stopped safely.",
                f"Page: {u}",
            ]
            if ti:
                lines.append(f"Title: {ti}")
            if ctx:
                lines.append("")
                lines.append("What was tried / current state (summary):")
                lines.append(ctx[:3200])
            lines.append("")
            lines.append("Reply with clearer constraints or a different approach if you want to continue.")
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


def _stuck_context_note(agent_output: Any, reply_lang: str) -> str:
    """HITL stuck_subgoal için kullanıcıya giden özet (DOM indeksi yok)."""
    cs = getattr(agent_output, "current_state", None) if agent_output else None
    if cs is None:
        return ""
    ev = str(getattr(cs, "evaluation_previous_goal", None) or "").strip()
    mem = str(getattr(cs, "memory", None) or "").strip()
    ng = str(getattr(cs, "next_goal", None) or "").strip()
    if reply_lang == "tr":
        parts: list[str] = []
        if ev:
            parts.append(f"Son değerlendirme: {ev[:1600]}")
        if mem:
            parts.append(f"Hafıza: {mem[:1600]}")
        if ng:
            parts.append(f"Tekrarlanan hedef: {ng[:800]}")
        return "\n".join(parts)[:3500]
    parts_en: list[str] = []
    if ev:
        parts_en.append(f"Last evaluation: {ev[:1600]}")
    if mem:
        parts_en.append(f"Memory: {mem[:1600]}")
    if ng:
        parts_en.append(f"Repeated goal: {ng[:800]}")
    return "\n".join(parts_en)[:3500]


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
        "auth_error_streak": 0,
        "last_auth_error_sig": None,
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
        user_blob = combined_for_lang
        lang = (reply_lang or infer_reply_language(combined_for_lang)).lower()
        if lang not in ("tr", "en"):
            lang = "en"
        cached = get_cached_agent(thread_id)
        continuation = bool(hints_list) or (
            cached is not None and _should_followup_on_live_session(thread_id, task)
        )
        full_task = _merge_task(task, hints_list, lang)
        if continuation and cached is not None and not hints_list:
            lu = get_thread_last_browser_url(thread_id) or "(unknown — inspect current tab)"
            full_task = (
                full_task
                + "\n\n[Session] Run mode: followup_on_live_session. The browser tab is already open in this chat. "
                "Do not navigate to the site's landing or home URL unless the task explicitly requires a full restart "
                "or the current page is clearly wrong. Prefer continuing from the current URL and session state.\n"
                f"Last known URL: {lu}\n"
            )
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
            if url:
                record_thread_last_browser_url(tid, url)
            png = _to_png_bytes(getattr(browser_state, "screenshot", None))
            if png:
                ctx["shot"] = png
            ft = str(ctx.get("full_task") or "")
            hl = ctx.get("hints_list") or []
            if not _looks_like_login_surface(url, title):
                ctx["login_surface_dom_defers"] = 0
                ctx["auth_error_streak"] = 0
                ctx["last_auth_error_sig"] = None

            corrections = await drain_mid_run_corrections(tid)
            if corrections:
                ctx["reason"] = "user_mid_run_message"
                ctx["agent_context"] = "\n---\n".join(corrections)[:2500]
                ctx["stop"] = True
                logger.info(
                    "HITL trigger: mid-run user message(s) count=%s thread_id=%s",
                    len(corrections),
                    tid,
                )
                await _maybe_emit_agent_progress_narration(tid, step, agent_output)
                return

            auth_sig = _auth_failure_class_from_agent_state(agent_output)
            th = self._settings.auth_failure_escalation_threshold
            if auth_sig is None:
                ctx["auth_error_streak"] = 0
                ctx["last_auth_error_sig"] = None
            elif _looks_like_login_surface(url, title) and _task_has_actionable_login_creds(ft):
                prev = ctx.get("last_auth_error_sig")
                if prev == auth_sig:
                    ctx["auth_error_streak"] = int(ctx.get("auth_error_streak") or 0) + 1
                else:
                    ctx["auth_error_streak"] = 1
                ctx["last_auth_error_sig"] = auth_sig
                if int(ctx["auth_error_streak"]) >= th:
                    ctx["reason"] = "repeated_auth_failure"
                    ctx["agent_context"] = _agent_context_blurb(agent_output)
                    ctx["stop"] = True
                    logger.info(
                        "HITL trigger: repeated auth failure streak=%s sig=%s thread_id=%s",
                        ctx["auth_error_streak"],
                        auth_sig,
                        tid,
                    )
                    await _maybe_emit_agent_progress_narration(tid, step, agent_output)
                    return
            else:
                ctx["auth_error_streak"] = 0
                ctx["last_auth_error_sig"] = None

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
                    if _task_has_actionable_login_creds(ft):
                        logger.info(
                            "HITL defer: görevde satır içi giriş bilgisi — iç ajanın doldurmasına izin veriliyor"
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
                if _agent_suggests_sensitive(agent_output, url, title):
                    ctx["reason"] = "model_indicated_sensitive_step"
                    ctx["agent_context"] = _agent_context_blurb(agent_output)
                    ctx["stop"] = True
                    logger.info("HITL trigger: agent output suggests sensitive step")
                    await _maybe_emit_agent_progress_narration(tid, step, agent_output)
                    return

            if not ctx.get("stop") and not _looks_like_login_surface(url, title):
                try:
                    ld = getattr(getattr(agent, "state", None), "loop_detector", None)
                    if ld is not None:
                        st_th = int(self._settings.browser_stuck_stagnation_threshold)
                        rp_th = int(self._settings.browser_stuck_repetition_threshold)
                        if ld.consecutive_stagnant_pages >= st_th or ld.max_repetition_count >= rp_th:
                            ctx["reason"] = "stuck_subgoal"
                            ctx["agent_context"] = _stuck_context_note(
                                agent_output, str(ctx.get("reply_lang") or "en")
                            )
                            ctx["stop"] = True
                            logger.info(
                                "HITL trigger: stuck_subgoal stagnant=%s repetition=%s thread_id=%s",
                                ld.consecutive_stagnant_pages,
                                ld.max_repetition_count,
                                tid,
                            )
                            await _maybe_emit_agent_progress_narration(tid, step, agent_output)
                            return
                except Exception:
                    logger.debug("loop/stuck detector skipped", exc_info=True)

            await _maybe_emit_agent_progress_narration(tid, step, agent_output)

        async def should_stop() -> bool:
            if is_stop_requested(tid):
                return True
            return bool(_run_ctx_for(tid)["stop"])

        from browser_use import Agent

        browser_session = await get_session(thread_id, self._settings)
        attach_navigate_policy(browser_session, build_navigate_policy_from_task(user_blob))
        _urls_for_ground = extract_all_http_urls(user_blob)
        _ground_truth = "\n".join(_urls_for_ground[:30]) if _urls_for_ground else None
        _agent_extras = {
            "tools": build_ghost_guarded_tools(),
            "extend_system_message": _AGENT_EXTEND_SYSTEM_MESSAGE,
            "ground_truth": _ground_truth,
        }
        try:
            if continuation and cached is not None:
                agent = cached
                agent.add_new_task(full_task)
                if hints_list:
                    logger.info(
                        "Aynı browser-use Agent ile devam (add_new_task) thread_id=%s — HITL / kullanıcı ipuçları",
                        tid,
                    )
                else:
                    logger.info(
                        "Aynı browser-use Agent ile devam (add_new_task) thread_id=%s — followup_on_live_session",
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
                    **_agent_extras,
                )
                set_cached_agent(thread_id, agent)
            else:
                if cached is not None:
                    await dispose_cached_agent(thread_id)
                    clear_thread_browser_continuity(thread_id)
                agent = Agent(
                    task=full_task,
                    llm=self._llm(),
                    browser_session=browser_session,
                    register_new_step_callback=on_step,
                    register_should_stop_callback=should_stop,
                    step_timeout=self._settings.browser_step_timeout,
                    **_agent_extras,
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
                record_thread_last_browser_url(thread_id, holder.get("url"))
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
            last_u = holder.get("url") or ""
            if _looks_like_login_surface(last_u, "") and _summary_asks_for_credentials(summary):
                record_pending_hitl(thread_id, last_u, "login_or_auth_surface")
                logger.info(
                    "done metni kimlik istiyor — pending HITL kaydı thread_id=%s",
                    thread_id,
                )
            else:
                clear_pending_hitl(thread_id)
            record_thread_last_browser_url(thread_id, holder.get("url"))
            _clear_run_ctx(thread_id)
            return BrowserRunResult(
                status=BrowserRunStatus.DONE,
                summary=summary,
                last_url=holder.get("url"),
                screenshot_png=holder.get("shot"),
            )
        finally:
            await mark_browser_run_idle(tid)
