"""Dış LLM'in araç çağırmadan 'captcha / manuel giriş' demesini azaltmak için sinyaller."""

from __future__ import annotations

from collections.abc import Sequence

from langchain_core.messages import BaseMessage, HumanMessage


def _human_text(content: str | list) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(str(block.get("text", "")))
                elif "text" in block:
                    parts.append(str(block["text"]))
            elif isinstance(block, str):
                parts.append(block)
        return " ".join(parts)
    return str(content)


def should_force_run_browser_automation(messages: Sequence[BaseMessage]) -> bool:
    """Son kullanıcı mesajı gerçek tarayıcı otomasyonu gerektiriyorsa True.

    Yalnızca son mesaj HumanMessage iken değerlendirilir (araç çıktısı / özet turunda False).
    """
    if not messages:
        return False
    last = messages[-1]
    if not isinstance(last, HumanMessage):
        return False
    t = _human_text(last.content).strip().lower()
    if len(t) < 8:
        return False
    if "http://" in t or "https://" in t:
        return True
    cues = (
        "obs.",
        "öğrenci giriş",
        "ogrenci giris",
        "ders program",
        "genel işlem",
        "genel islem",
        "siteye git",
        "adrese git",
        "giriş yap",
        "giris yap",
        "ekran görüntü",
        "ekran goruntu",
        "screenshot",
        "student login",
        "log in",
        "sign in",
    )
    return any(c in t for c in cues)
