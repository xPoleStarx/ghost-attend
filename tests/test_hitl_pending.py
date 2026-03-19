from app.adapters.hitl_pending import (
    clear_pending_hitl,
    record_pending_hitl,
    take_synthetic_hints_if_orphan,
)


def test_orphan_synthetic_once():
    tid = "t1"
    record_pending_hitl(tid, "https://ex.com/login", "login_or_auth_surface")
    h1 = take_synthetic_hints_if_orphan(tid)
    assert h1 is not None
    assert "https://ex.com/login" in h1[0]
    assert take_synthetic_hints_if_orphan(tid) is None


def test_clear_removes_pending():
    tid = "t2"
    record_pending_hitl(tid, None, None)
    clear_pending_hitl(tid)
    assert take_synthetic_hints_if_orphan(tid) is None
