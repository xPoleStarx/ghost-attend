from app.services.recovery import RecoveryService


def test_recovery_service_builds_plan_from_session_metadata() -> None:
    service = RecoveryService()

    plan = service.build_recovery_plan(
        user_id=7,
        session_id="session-1",
        session_metadata={"requires_login": False},
    )

    assert plan.user_id == 7
    assert plan.session_id == "session-1"
    assert plan.requires_login is False
