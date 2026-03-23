"""browser_action_guard ve gezinme readiness yardımcıları."""

from app.adapters.browser_action_guard import (
    build_navigate_policy_from_task,
    validate_evaluate_code,
    validate_find_elements_params,
    validate_navigate_url,
)
from app.adapters.browser_session_holder import resolve_nav_readiness_timeout_seconds
from app.adapters.browser_use_runner import _authoritative_targets_block, _merge_task, extract_all_http_urls


def test_extract_all_http_urls_order_and_dedupe():
    t = "See https://a.com/x and https://b.com then https://a.com/x"
    assert extract_all_http_urls(t) == ["https://a.com/x", "https://b.com"]


def test_merge_task_includes_authoritative_block():
    task = "[reply-lang:en]\n\nOpen https://www.youtube.com/@EnesBatur/videos\n"
    merged = _merge_task(task, [], "en")
    assert "[Authoritative user targets" in merged
    assert "youtube.com/@EnesBatur/videos" in merged
    assert "Never navigate to a different YouTube @handle" in merged


def test_authoritative_targets_block_empty_without_urls():
    assert _authoritative_targets_block([]) == ""


def test_validate_evaluate_rejects_typos():
    assert validate_evaluate_code("document.querySelectorAlll('x')") is not None
    assert validate_evaluate_code("(function(){return 1})()") is None


def test_validate_evaluate_unbalanced():
    assert validate_evaluate_code("(function(){return 1") is not None


def test_validate_find_elements_bad_attribute():
    err = validate_find_elements_params("div", ["ariaa-label"])
    assert err is not None
    assert "ariaa-label" in err or "Unsupported" in err


def test_validate_find_elements_bad_selector_fragment():
    err = validate_find_elements_params("yt--chip-cloud-chip-renderer", None)
    assert err is not None


def test_youtube_navigate_policy_blocks_other_handle():
    task = "Go to https://www.youtube.com/@EnesBatur/videos"
    pol = build_navigate_policy_from_task(task)
    assert validate_navigate_url("https://www.youtube.com/@newdaynewgame/videos", pol) is not None
    assert validate_navigate_url("https://www.youtube.com/@EnesBatur/videos", pol) is None


def test_navigate_rejects_sortt_typo():
    assert validate_navigate_url("https://example.com/?sortt=p", None) is not None


def test_resolve_nav_youtube_same_site_uses_full_readiness():
    t = resolve_nav_readiness_timeout_seconds(
        "https://www.youtube.com/@x/videos",
        "https://www.youtube.com/",
        full_readiness=18.0,
        same_origin_timeout=5.0,
        always_full_readiness_hosts_csv="youtube.com,www.youtube.com,m.youtube.com",
    )
    assert t == 18.0


def test_resolve_nav_same_origin_non_listed_uses_same_origin_timeout():
    t = resolve_nav_readiness_timeout_seconds(
        "https://example.com/b",
        "https://example.com/a",
        full_readiness=20.0,
        same_origin_timeout=12.0,
        always_full_readiness_hosts_csv="youtube.com",
    )
    assert t == 12.0


def test_resolve_nav_cross_origin_full():
    t = resolve_nav_readiness_timeout_seconds(
        "https://b.com/",
        "https://a.com/",
        full_readiness=20.0,
        same_origin_timeout=12.0,
        always_full_readiness_hosts_csv="youtube.com",
    )
    assert t == 20.0
