import pytest

from app.app import GhostAttendApplication
from app.config import Settings


@pytest.mark.asyncio
async def test_application_startup_returns_bootstrap_snapshot() -> None:
    settings = Settings(
        DATABASE_URL="sqlite+aiosqlite:///:memory:",
        REDIS_URL="redis://localhost:6379/0",
        SECRET_KEY="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
    )
    app = GhostAttendApplication.build(settings)

    result = await app.startup()

    assert "scheduled_course_count" in result
    assert "recovery_plan_count" in result
    await app.shutdown()
