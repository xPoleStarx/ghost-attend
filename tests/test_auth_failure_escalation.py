"""Tekrarlayan giriş hatası sınıflandırması ve görevde kimlik tespiti."""

from __future__ import annotations

from types import SimpleNamespace

from app.adapters.browser_use_runner import (
    _auth_failure_class_from_agent_state,
    _hitl_question,
    _summary_asks_for_credentials,
    _task_has_actionable_login_creds,
)


def _state(ev: str, mem: str) -> SimpleNamespace:
    return SimpleNamespace(
        current_state=SimpleNamespace(
            evaluation_previous_goal=ev,
            memory=mem,
            next_goal="",
        )
    )


def test_auth_failure_detects_turkish_obs_message():
    st = _state(
        "Giriş denemesi 'Kullanıcı Adı veya Şifre Yanlış Girilmiştir' hatasıyla sonuçlandı. Sonuç: Başarısız.",
        "OBS giriş sayfasındayım.",
    )
    assert _auth_failure_class_from_agent_state(st) == "invalid_credentials"


def test_auth_failure_detects_short_turkish_variant():
    st = _state(
        "Eval: Giriş denemesi 'Kullanıcı Adı veya Şifre Yanlış' hatası nedeniyle başarısız oldu.",
        "",
    )
    assert _auth_failure_class_from_agent_state(st) == "invalid_credentials"


def test_auth_failure_detects_english():
    st = _state("The login failed: incorrect password.", "")
    assert _auth_failure_class_from_agent_state(st) == "invalid_credentials"


def test_auth_failure_none_when_empty():
    assert _auth_failure_class_from_agent_state(None) is None
    assert _auth_failure_class_from_agent_state(SimpleNamespace(current_state=None)) is None


def test_actionable_creds_username_password_obs_style():
    t = (
        "1. https://obs.mu.edu.tr/ adresine git.\n"
        "2. Kullanıcı adı: seyfullahkorkmaz, Şifre: Seyfo46500. bilgilerini kullanarak giriş yap."
    )
    assert _task_has_actionable_login_creds(t)


def test_actionable_creds_email_password_still_true():
    t = "user@school.edu / mySecret1 ile giriş yap."
    assert _task_has_actionable_login_creds(t)


def test_summary_asks_for_credentials_turkish():
    s = (
        "Muğla Sıtkı Koçman Üniversitesi OBS giriş sayfasına ulaştım. "
        "Devam edebilmem için lütfen kullanıcı adınızı ve şifrenizi paylaşır mısınız?"
    )
    assert _summary_asks_for_credentials(s)


def test_hitl_question_repeated_auth_failure_turkish():
    q = _hitl_question(
        "https://obs.mu.edu.tr/login.aspx",
        "Giriş",
        "repeated_auth_failure",
        agent_context="Deneme özeti",
        reply_lang="tr",
    )
    assert "birkaç kez" in q.lower() or "birkaç" in q
    assert "yanlış" in q.lower()
    assert "nokta" in q.lower() or "karakter" in q.lower()


def test_hitl_question_mid_run_turkish():
    q = _hitl_question(
        "https://example.com/login",
        None,
        "user_mid_run_message",
        agent_context="şifre sonunda nokta var",
        reply_lang="tr",
    )
    assert "mesaj" in q.lower()
    assert "nokta" in q or "şifre" in q
