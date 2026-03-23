"""Tarayıcı aracı yüklerini çalıştırmadan önce doğrulama — hayali URL, bozuk seçiciler, typo JS."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

_YT_CHANNEL_URL = re.compile(
    r"(?:https?://)?(?:www\.|m\.)?youtube\.com/@([^/?#\s]+)",
    re.IGNORECASE,
)

# find_elements: izinli DOM öznitelik adları (browser_use örnekleriyle uyumlu)
_FIND_ELEMENTS_ALLOWED_ATTRS: frozenset[str] = frozenset(
    {
        "aria-label",
        "class",
        "id",
        "role",
        "href",
        "src",
        "title",
        "name",
        "type",
        "value",
        "placeholder",
        "data-testid",
        "tabindex",
        "alt",
        "for",
    }
)

# Bilinen model yazım hataları / halüsinasyon kalıpları
_EVAL_FORBIDDEN_SUBSTRINGS: tuple[str, ...] = (
    "querySelectorAlll",
    "queryySelector",
    "queerySelector",
    "querySelecttor",
    "querySelecttorAll",
    "getElementByIdd",
    "getElementsByTagNamee",
    "document.evaluatee",
    "yyt-chip-cloud-chip-renderer",
    "yt--chip-cloud-chip-renderer",
    "yt-formatted-strinng",
)

_SELECTOR_FORBIDDEN_SNIPPETS: tuple[str, ...] = (
    "yyt-chip",
    "yt--chip",
    "yt-formatted-strinng",
    "strinng",
    "tabb'",
    'tabb"',
)


@dataclass(frozen=True)
class NavigatePolicy:
    """Görev metninden çıkarılan YouTube @handle kısıtı; boş küme = kısıt yok."""

    allowed_youtube_handles_lower: frozenset[str]


def build_navigate_policy_from_task(task_text: str) -> NavigatePolicy:
    """Görevde youtube.com/@… geçiyorsa bu handle'lar yetkili sayılır; aksi halde kısıt yok."""
    if not task_text or not re.search(r"youtube\.com/@", task_text, re.IGNORECASE):
        return NavigatePolicy(frozenset())
    handles = {m.group(1).lower() for m in _YT_CHANNEL_URL.finditer(task_text)}
    return NavigatePolicy(frozenset(handles))


def validate_navigate_url(url: str, policy: NavigatePolicy | None) -> str | None:
    """Geçersizse kısa İngilizce hata metni; geçerliyse None."""
    if not url or not str(url).strip():
        return "Empty navigate URL."
    raw = str(url).strip()
    low = raw.lower()
    if "sortt=" in low:
        return "Malformed URL query: typo sortt= — use sort= (or omit query params)."
    if policy is None or not policy.allowed_youtube_handles_lower:
        return None
    try:
        p = urlparse(raw)
    except Exception:
        return "Unparseable navigate URL."
    host = (p.netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if not host.endswith("youtube.com"):
        return None
    m = re.search(r"/@([^/?#]+)", p.path or "")
    if not m:
        return None
    handle = m.group(1).lower()
    if handle not in policy.allowed_youtube_handles_lower:
        allowed = ", ".join(f"@{h}" for h in sorted(policy.allowed_youtube_handles_lower))
        return (
            f"Navigation to @{handle} is not allowed: the user task only authorizes these channel paths: {allowed}. "
            "Do not invent or switch channel handles."
        )
    return None


def _js_delimiters_balanced(code: str) -> bool:
    """Basit ayraç dengesi (dize kaçışları hariç — hızlı sezgisel kontrol)."""
    stack: list[str] = []
    pairs = {"(": ")", "[": "]", "{": "}"}
    closers = {")", "]", "}"}
    for c in code:
        if c in pairs:
            stack.append(pairs[c])
        elif c in closers:
            if not stack or stack[-1] != c:
                return False
            stack.pop()
    return not stack


def validate_evaluate_code(code: str | None) -> str | None:
    """Geçersizse hata metni; geçerliyse None."""
    if code is None:
        return "Missing JavaScript code for evaluate."
    s = str(code).strip()
    if not s:
        return "Empty JavaScript code for evaluate."
    if not _js_delimiters_balanced(s):
        return "JavaScript appears to have unbalanced (), [] or {} — fix syntax before evaluate."
    low = s
    for bad in _EVAL_FORBIDDEN_SUBSTRINGS:
        if bad in low:
            return f"Suspicious or typo JavaScript fragment ({bad!r}) — fix DOM API spelling."
    if re.search(r"document\.query\s*Selector", low) and "document.querySelector" not in low.replace(" ", ""):
        pass  # too noisy
    if re.search(r"document\.queryy", low):
        return "Typo in document.querySelector — remove repeated letters."
    if re.search(r"document\.queery", low):
        return "Typo: queerySelector — use querySelector / querySelectorAll."
    return None


def validate_find_elements_params(
    selector: str | None,
    attributes: list[str] | None,
) -> str | None:
    """find_elements argümanları için kısa hata veya None."""
    sel = (selector or "").strip()
    if not sel:
        return "find_elements requires a non-empty selector."
    for frag in _SELECTOR_FORBIDDEN_SNIPPETS:
        if frag in sel:
            return f"Selector contains a likely typo or invalid fragment ({frag!r})."
    if attributes is None:
        return None
    bad = [a for a in attributes if a not in _FIND_ELEMENTS_ALLOWED_ATTRS]
    if bad:
        return (
            f"Unsupported attribute name(s) in find_elements: {bad!r}. "
            f"Use only: {', '.join(sorted(_FIND_ELEMENTS_ALLOWED_ATTRS))}."
        )
    return None


def attach_navigate_policy(browser_session: Any, policy: NavigatePolicy) -> None:
    """BrowserSession üzerinde çalışma boyunca navigate doğrulaması için politika."""
    setattr(browser_session, "_ghost_nav_policy", policy)


def clear_navigate_policy(browser_session: Any) -> None:
    if browser_session is not None and hasattr(browser_session, "_ghost_nav_policy"):
        try:
            delattr(browser_session, "_ghost_nav_policy")
        except Exception:
            setattr(browser_session, "_ghost_nav_policy", None)
