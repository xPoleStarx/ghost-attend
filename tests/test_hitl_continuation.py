"""HITL sonrası devam bağlamı: otomatik blok ve görev birleştirme."""

from types import SimpleNamespace

from app.adapters.browser_use_runner import (
    _login_dom_looks_unready,
    _merge_task,
    _task_has_inline_credentials,
    _task_suppresses_login_surface_hitl,
    infer_reply_language,
    parse_reply_lang_directive,
)
from app.agent.tools import _continuation_block_after_hitl
from app.domain.schemas import BrowserRunResult, BrowserRunStatus


def test_continuation_block_includes_reason_and_url():
    r = BrowserRunResult(
        status=BrowserRunStatus.NEEDS_HUMAN,
        summary="",
        last_url="https://example.com/login",
        history_tail="step done",
        hitl_reason="login_or_auth_surface",
    )
    block = _continuation_block_after_hitl(r)
    assert "login or identity" in block
    assert "https://example.com/login" in block
    assert "step done" in block
    assert "re-run" in block.lower() or "numbered" in block.lower()


def test_continuation_truncates_long_tail():
    long_tail = "x" * 5000
    r = BrowserRunResult(
        status=BrowserRunStatus.NEEDS_HUMAN,
        summary="",
        last_url=None,
        history_tail=long_tail,
        hitl_reason=None,
    )
    block = _continuation_block_after_hitl(r)
    assert "truncated" in block
    assert len(block) < len(long_tail) + 500


def test_merge_task_with_hints_adds_resume_priority():
    merged = _merge_task("1. Go to A\n2. Do B", ["user said ok", "[auto] ctx"], "en")
    assert "[Resume turn]" in merged
    assert "Do not repeat" in merged
    assert "[Additional input from the user]" in merged
    assert "user said ok" in merged


def test_parse_reply_lang_directive():
    lang, rest = parse_reply_lang_directive("[reply-lang:TR]\n\nGo to example.com")
    assert lang == "tr"
    assert rest.startswith("Go to")


def test_infer_reply_language_turkish_chars():
    assert infer_reply_language("Şifremi unuttum") == "tr"


def test_infer_reply_language_english_default():
    assert infer_reply_language("Open example.com and search") == "en"


def test_login_hitl_suppressed_when_task_says_no_login():
    t = "Go to dys.mu.edu.tr. Do not attempt to log in yet, just confirm you are at the login screen."
    assert _task_suppresses_login_surface_hitl(t)
    assert not _task_suppresses_login_surface_hitl("Log in and download all grades")


def test_inline_credentials_detected():
    t = (
        "Go to dys.mu.edu.tr. Enter the username 'u@posta.mu.edu.tr' and password 'Secret12.' "
        "and click login."
    )
    assert _task_has_inline_credentials(t)
    assert not _task_has_inline_credentials("Open dys.mu.edu.tr and tell me the page title")


def test_login_dom_unready_empty_selector_map():
    st = SimpleNamespace(dom_state=SimpleNamespace(selector_map={}))
    assert _login_dom_looks_unready(st)


def test_login_dom_ready_enough_interactive_nodes():
    sm = {i: object() for i in range(8)}
    st = SimpleNamespace(dom_state=SimpleNamespace(selector_map=sm))
    assert not _login_dom_looks_unready(st)


def test_inline_credentials_email_slash_password():
    t = "Trendyol.com sitesine git ve seyfullahkorkmaz115@gmail.com / 123456 bilgileriyle giriş yap."
    assert _task_has_inline_credentials(t)
