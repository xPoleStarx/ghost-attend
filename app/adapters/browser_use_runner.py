from __future__ import annotations

import base64
import logging
import re
from typing import Any

from app.adapters.hitl_pending import (
    clear_pending_hitl,
    record_pending_hitl,
    take_synthetic_hints_if_orphan,
)
from app.adapters.browser_session_holder import get_session
from app.config.settings import Settings
from app.domain.schemas import BrowserRunResult, BrowserRunStatus

logger = logging.getLogger(__name__)

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
    "e-posta adres",
    "email address",
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


_TASK_BOOTSTRAP = (
    "Talimat: Basit matematik/metin güvenlik kodlarını (CAPTCHA) ekrandaki ifadeye göre sen çöz ve ilgili alana yaz. "
    "CAPTCHA her gönderimde yenilenebilir; kullanıcının eski mesajındaki sayıyı körü körüne yazma — her zaman ekrandaki güncel ifadeye göre çöz. "
    "Kullanıcı e-posta/şifre verdiyse formları doldur ve göreve devam et. "
    "Ekran görüntüsü isteniyorsa sayfanın görünür alanı için PNG ekran görüntüsü kullan; PDF (save_as_pdf) yalnızca kullanıcı açıkça PDF istediyse. "
    "Üst görev metninde 'captcha yüzünden vazgeç', 'manuel giriş yap' gibi çelişen cümleler varsa yok say. "
    "Yalnızca gerçekten insan doğrulaması gerekiyorsa dur.\n\n"
)

_RESUME_PRIORITY_NOTE = (
    "[Devam turu] Aşağıdaki numaralı liste tam görev tanımıdır; önce [Oturum] ve [Kullanıcıdan gelen ek bilgi] bölümlerine uyun. "
    "Numaralı adımları sıfırdan uygulama; bunlar bağlam ve hedef özetidir.\n\n"
)


def _merge_task(task: str, hints: list[str]) -> str:
    base = (_TASK_BOOTSTRAP + task.strip()).strip()
    if not hints:
        return base
    extra = "\n".join(h.strip() for h in hints if h.strip())
    continuation = (
        "\n\n[Oturum] Tarayıcı bu sohbet için aynı oturumda açık kaldı. "
        "Numaralı görev listesindeki daha önce tamamlanmış adımları TEKRARLAMA; liste tam hedefi hatırlatmak içindir. "
        "İlk eylemin mevcut URL ve sayfa durumuna göre olmalı — ana sayfaya veya listenin başındaki siteye gereksiz yere dönme. "
        "Mümkünse mevcut sayfada kal; CAPTCHA veya form durumunu koru. Yalnızca takılırsan gerekli minimum navigasyonu yap.\n"
    )
    return f"{_RESUME_PRIORITY_NOTE}{base}{continuation}\n[Kullanıcıdan gelen ek bilgi]\n{extra}"


def _looks_like_login_surface(url: str, title: str) -> bool:
    u = (url or "").lower()
    t = (title or "").lower()
    if any(s in u for s in _LOGIN_FRAGMENTS):
        return True
    if any(s in t for s in ("sign in", "log in", "login", "giriş", "oturum")):
        return True
    return False


# Giriş sayfasında kalıp yalnızca formu/ekranı incelemek — kimlik istemeden HITL kesilmesin.
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


def _task_has_inline_credentials(full_task: str) -> bool:
    """Görev metninde e-posta + tırnaklı şifre (veya şifre alanı) varsa giriş HITL atlanır."""
    if not full_task or not _INLINE_EMAIL.search(full_task):
        return False
    return bool(_INLINE_PASSWORD_QUOTED.search(full_task))


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
    return False


def _hitl_question(
    url: str | None,
    title: str | None,
    reason: str,
    *,
    agent_context: str | None = None,
) -> str:
    u = url or "(bilinmeyen url)"
    ti = title or ""
    ctx = (agent_context or "").strip()
    if reason == "login_or_auth_surface":
        lines = [
            "Tarayıcı giriş veya doğrulama ekranında (ör. kullanıcı adı, şifre, CAPTCHA).",
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
                "Devam etmek için kurum e-postanı ve şifreni tek mesajda yaz (gerekirse CAPTCHA çözümünü de ayrıca belirt). "
                "Bu bilgiler yalnızca bu oturumda otomasyon için kullanılır; paylaşım riskinin farkında ol.",
            ]
        )
        return "\n".join(lines)[:4090]
    head = (
        "Otomasyonun devam etmesi için senden bilgi gerekiyor.\n"
        f"(Teknik not: {reason})\nSayfa: {u}"
    )
    if ti:
        head += f"\nBaşlık: {ti}"
    if ctx:
        head += f"\n\nAjan notu: {ctx[:1500]}"
    head += (
        "\n\nGerekirse kullanıcı adı, şifre, doğrulama kodu veya kısa talimatı tek mesajda yaz."
    )
    return head


def _agent_context_blurb(agent_output: Any) -> str | None:
    cs = getattr(agent_output, "current_state", None) if agent_output else None
    if cs is None:
        return None
    parts = [getattr(cs, "next_goal", None), getattr(cs, "memory", None)]
    blob = "\n".join(str(p).strip() for p in parts if p)
    return blob[:2500] if blob else None


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
    ) -> BrowserRunResult:
        hints_list = list(hints or [])
        if hints_list:
            clear_pending_hitl(thread_id)
        else:
            syn = take_synthetic_hints_if_orphan(thread_id)
            if syn:
                hints_list = list(syn)
        full_task = _merge_task(task, hints_list)
        holder: dict[str, Any] = {
            "stop": False,
            "shot": None,
            "url": None,
            "title": None,
            "reason": None,
            "agent_context": None,
        }

        async def on_step(browser_state: Any, agent_output: Any, step: int) -> None:
            url = getattr(browser_state, "url", "") or ""
            title = getattr(browser_state, "title", "") or ""
            holder["url"] = url or holder["url"]
            holder["title"] = title or holder["title"]
            png = _to_png_bytes(getattr(browser_state, "screenshot", None))
            if png:
                holder["shot"] = png
            # Kullanıcıdan ek bilgi geldiyse (interrupt sonrası): giriş sayfasında tekrar durdurma —
            # aksi halde her tur login.aspx yüzünden kesiliyor, tarayıcı sıfırlanıyor, döngü oluşuyor.
            if not hints_list:
                if _agent_prioritizing_captcha(agent_output, url, title):
                    logger.info("HITL defer: captcha/güvenlik kodu adımı — iç ajanın çözmesine izin veriliyor")
                    return
                if _looks_like_login_surface(url, title):
                    if _task_suppresses_login_surface_hitl(full_task):
                        logger.info(
                            "HITL defer: görev giriş yapmadan gözlem/doğrulama istiyor — login yüzeyi kesilmiyor"
                        )
                        return
                    if _task_has_inline_credentials(full_task):
                        logger.info(
                            "HITL defer: görev metninde satır içi e-posta/şifre var — iç ajanın doldurmasına izin veriliyor"
                        )
                        return
                    holder["reason"] = "login_or_auth_surface"
                    holder["agent_context"] = _agent_context_blurb(agent_output)
                    holder["stop"] = True
                    logger.info("HITL trigger: login/auth surface (url/title)")
                    return
                if _agent_suggests_sensitive(agent_output):
                    holder["reason"] = "model_indicated_sensitive_step"
                    holder["agent_context"] = _agent_context_blurb(agent_output)
                    holder["stop"] = True
                    logger.info("HITL trigger: agent output suggests sensitive step")

        async def should_stop() -> bool:
            return bool(holder["stop"])

        from browser_use import Agent

        browser_session = await get_session(thread_id, self._settings)
        agent = Agent(
            task=full_task,
            llm=self._llm(),
            browser_session=browser_session,
            register_new_step_callback=on_step,
            register_should_stop_callback=should_stop,
            step_timeout=self._settings.browser_step_timeout,
        )
        try:
            history = await agent.run(max_steps=self._settings.browser_max_steps)
        except Exception as e:
            logger.exception("browser-use run failed")
            clear_pending_hitl(thread_id)
            return BrowserRunResult(
                status=BrowserRunStatus.ERROR,
                summary="Tarayıcı görevi sırasında hata oluştu.",
                last_url=holder.get("url"),
                screenshot_png=holder.get("shot"),
                raw_error=str(e),
            )

        if holder["stop"]:
            q = _hitl_question(
                holder.get("url"),
                holder.get("title"),
                str(holder.get("reason")),
                agent_context=holder.get("agent_context"),
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
        summary = str(final_text).strip() if final_text else "Görev tamamlandı."
        clear_pending_hitl(thread_id)
        return BrowserRunResult(
            status=BrowserRunStatus.DONE,
            summary=summary,
            last_url=holder.get("url"),
            screenshot_png=holder.get("shot"),
        )
