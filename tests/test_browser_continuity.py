"""Takip görevi / aynı Agent devamı, URL çıkarımı ve HITL sensitive yanlış pozitif."""

from types import SimpleNamespace
from unittest.mock import patch

from app.adapters.browser_use_runner import (
    _agent_suggests_sensitive,
    _should_followup_on_live_session,
    extract_primary_http_url,
    sites_match_for_continuity,
)


def test_extract_primary_http_url():
    assert (
        extract_primary_http_url("Git https://obs.mu.edu.tr/ ve giriş yap")
        == "https://obs.mu.edu.tr/"
    )
    assert extract_primary_http_url("no url here") is None


def test_sites_match_for_continuity_ignores_www():
    assert sites_match_for_continuity("https://www.example.com/a", "https://example.com/b")
    assert not sites_match_for_continuity("https://a.com", "https://b.com")
    assert not sites_match_for_continuity("", "https://b.com")


def test_should_followup_when_no_url_in_task():
    with patch(
        "app.adapters.browser_use_runner.get_thread_last_browser_url",
        return_value="https://obs.mu.edu.tr/x",
    ):
        assert _should_followup_on_live_session("tid1", "Ders programını listele")


def test_should_followup_false_when_different_host():
    with patch(
        "app.adapters.browser_use_runner.get_thread_last_browser_url",
        return_value="https://obs.mu.edu.tr/x",
    ):
        assert not _should_followup_on_live_session(
            "tid1",
            "https://google.com/ ara",
        )


def test_agent_sensitive_suppressed_post_credential_tr_on_non_login():
    """Giriş sonrası 'şifre girildi' hafızası — model_indicated_sensitive_step tetiklenmemeli."""
    agent_output = SimpleNamespace(
        current_state=SimpleNamespace(
            memory="Kullanıcı adı, şifre ve güvenlik kodu girildi. Sayfa yükleniyor.",
            next_goal="Sistemin yüklenmesi için bekliyorum.",
            evaluation_previous_goal="Belirsiz (Yükleniyor).",
        )
    )
    assert not _agent_suggests_sensitive(
        agent_output,
        "https://obs.mu.edu.tr/oibs/std/index.aspx",
        "Öğrenci paneli",
    )


def test_agent_sensitive_still_triggers_otp_off_login_surface():
    agent_output = SimpleNamespace(
        current_state=SimpleNamespace(
            memory="Uygulama doğrulama kodu istiyor.",
            next_goal="Kullanıcıdan OTP iste.",
            evaluation_previous_goal="",
        )
    )
    assert _agent_suggests_sensitive(
        agent_output,
        "https://obs.mu.edu.tr/app/settings",
        "Ayarlar",
    )


def test_agent_sensitive_login_surface_keeps_password_terms():
    agent_output = SimpleNamespace(
        current_state=SimpleNamespace(
            memory="Şifre alanı boş.",
            next_goal="Şifre gir.",
            evaluation_previous_goal="",
        )
    )
    assert _agent_suggests_sensitive(
        agent_output,
        "https://site.com/login",
        "Sign in",
    )
