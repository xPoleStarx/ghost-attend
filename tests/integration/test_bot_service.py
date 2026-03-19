from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import pytest

from app.bot.service import GhostAttendBotService


@dataclass
class FakeUser:
    id: int
    telegram_id: int
    timezone: str


@dataclass
class FakeSession:
    id: object


@dataclass
class FakeCourse:
    id: int
    name: str
    user_id: int = 1
    start_day_of_week_utc: str = "MONDAY"
    start_time_utc: str = "11:00"
    is_active: bool = True


class FakeUserRepository:
    def __init__(self) -> None:
        self.user: FakeUser | None = None

    async def get_by_telegram_id(self, telegram_id: int) -> FakeUser | None:
        if self.user is not None and self.user.telegram_id == telegram_id:
            return self.user
        return None

    async def create(self, **_: object) -> FakeUser:
        self.user = FakeUser(id=1, telegram_id=42, timezone="Europe/Istanbul")
        return self.user


class FakeCourseRepository:
    def __init__(self) -> None:
        self.courses: list[FakeCourse] = []

    async def create_many(self, user_id: int, rows: list[dict[str, str | None]]) -> list[FakeCourse]:
        self.courses = [
            FakeCourse(id=index + 1, name=str(row["name"]), user_id=user_id)
            for index, row in enumerate(rows)
        ]
        return self.courses

    async def list_active_for_user(self, user_id: int) -> list[FakeCourse]:
        return [course for course in self.courses if course.user_id == user_id]

    async def list_all_active(self) -> list[FakeCourse]:
        return self.courses


class FakeSessionRepository:
    def __init__(self) -> None:
        self.active: FakeSession | None = None

    async def get_active_for_user(self, user_id: int) -> FakeSession | None:
        _ = user_id
        return self.active

    async def create(self, user_id: int, metadata: dict[str, object] | None = None) -> FakeSession:
        _ = (user_id, metadata)
        self.active = FakeSession(id=uuid4())
        return self.active

    async def close_active_for_user(self, user_id: int) -> FakeSession | None:
        _ = user_id
        session = self.active
        self.active = None
        return session

    async def list_active(self) -> list[FakeSession]:
        return [] if self.active is None else [self.active]


class FakeBrowserContextManager:
    async def get_context(self, user_id: int) -> None:
        _ = user_id
        return None

    async def destroy_context(self, user_id: int) -> None:
        _ = user_id


class FakeSchedulerBootstrapService:
    async def bootstrap_all_active_courses(self) -> object:
        return type("Result", (), {"scheduled_course_count": 0, "scheduled_job_count": 0})()


class FakeRecoveryCoordinator:
    async def list_recovery_plans(self) -> list[object]:
        return []


class FakeOperatorSnapshotService:
    async def snapshot(self) -> dict[str, object]:
        return {"active_context_count": 0}


class FakeContainer:
    def __init__(self) -> None:
        from datetime import timedelta

        from app.config import Settings
        from app.security.crypto import CredentialCipher
        from app.services.conflicts import ScheduleConflictDetector
        from app.services.deduplication import CommandDeduplicator
        from app.services.llm_onboarding import LLMOnboardingAssistant
        from app.services.metrics import MetricsCollector
        from app.services.observability import ObservabilityService
        from app.services.onboarding_service import OnboardingService
        from app.services.rate_limit import SlidingWindowRateLimiter
        from app.services.recovery import RecoveryService
        from app.services.schedule_ingestion import ScheduleIngestionService, StubScheduleImageExtractor
        from app.services.schedule_parser import ScheduleParser
        from app.services.task_queue import TaskQueueGateway
        from app.services.timezone import TimezoneNormalizer

        self.user_repository = FakeUserRepository()
        self.course_repository = FakeCourseRepository()
        self.session_repository = FakeSessionRepository()
        self.browser_context_manager = FakeBrowserContextManager()
        self.rate_limiter = SlidingWindowRateLimiter(limit=100, window=timedelta(minutes=1))
        self.command_deduplicator = CommandDeduplicator(window=timedelta(seconds=30))
        self.scheduler_bootstrap_service = FakeSchedulerBootstrapService()
        self.recovery_coordinator = FakeRecoveryCoordinator()
        self.operator_snapshot_service = FakeOperatorSnapshotService()
        self.metrics = MetricsCollector()
        self.task_queue = TaskQueueGateway()
        self.observability_service = ObservabilityService(None, self.metrics)
        self.onboarding_service = OnboardingService(
            user_repository=self.user_repository,  # type: ignore[arg-type]
            course_repository=self.course_repository,  # type: ignore[arg-type]
            session_repository=self.session_repository,  # type: ignore[arg-type]
            cipher=CredentialCipher(
                raw_secret="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
                key_version="v1",
            ),
            schedule_ingestion=ScheduleIngestionService(
                parser=ScheduleParser(),
                image_extractor=StubScheduleImageExtractor(),
            ),
            timezone_normalizer=TimezoneNormalizer(),
            llm_assistant=LLMOnboardingAssistant(
                Settings(
                    DATABASE_URL="postgresql+asyncpg://ghost:ghost@db:5432/ghost_attend",
                    REDIS_URL="redis://redis:6379/0",
                    SECRET_KEY="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
                )
            ),
            conflict_detector=ScheduleConflictDetector(),
        )


class FakeRuntime:
    def __init__(self) -> None:
        from contextlib import asynccontextmanager
        from app.bot.handlers import BotStateStore

        self.bot_state_store = BotStateStore()
        self._container = FakeContainer()

        @asynccontextmanager
        async def container() -> object:
            yield self._container

        self.container = container

    def build_onboarding_coordinator(self, container: object) -> object:
        from app.bot.handlers import OnboardingCoordinator

        return OnboardingCoordinator(container.onboarding_service, self.bot_state_store)  # type: ignore[attr-defined]

    def build_agent_coordinator(self, container: object) -> object:
        from app.bot.handlers import AgentCoordinator
        from app.agent.dispatcher import AgentDispatcher
        from app.agent.runtime import AgentRuntimeService
        from app.domain.schemas import ToolResult

        class FakeJoinTool:
            async def __call__(self, params: object) -> ToolResult:
                _ = params
                return ToolResult(success=True, message="joined")

        class FakeLeaveTool:
            async def __call__(self, params: object) -> ToolResult:
                _ = params
                return ToolResult(success=True, message="left")

        class FakeScreenshotTool:
            async def __call__(self, params: object) -> ToolResult:
                _ = params
                return ToolResult(success=True, message="shot")

        class FakeHumanTool:
            async def __call__(self, params: object) -> ToolResult:
                _ = params
                return ToolResult(success=True, message="Human input requested: req-1")

        runtime = AgentRuntimeService(
            dispatcher=AgentDispatcher(
                tools={
                    "join_teams_meeting": FakeJoinTool(),
                    "leave_meeting": FakeLeaveTool(),
                    "take_screenshot": FakeScreenshotTool(),
                    "request_human_input": FakeHumanTool(),
                }
            )
        )
        return AgentCoordinator(
            runtime_service=runtime,
            rate_limiter=container.rate_limiter,  # type: ignore[attr-defined]
            deduplicator=container.command_deduplicator,  # type: ignore[attr-defined]
        )


@pytest.mark.asyncio
async def test_bot_service_start_returns_first_onboarding_prompt() -> None:
    service = GhostAttendBotService(FakeRuntime())  # type: ignore[arg-type]

    message = await service.handle_start(42)

    assert "Ghost Attend" in message


@pytest.mark.asyncio
async def test_bot_service_onboarding_completion_clears_draft() -> None:
    runtime = FakeRuntime()
    service = GhostAttendBotService(runtime)  # type: ignore[arg-type]

    await service.handle_start(42)
    await service.handle_text_message(
        42,
        "https://dys.example.edu adresim, student@example.edu mailim, sifrem pass123, Europe/Istanbul",
    )
    await service.handle_text_message(
        42,
        "Kariyer Planlama | monday | 14:00 | 15:00 | https://example.com",
    )
    message = await service.handle_text_message(42, "YES")

    assert "Onboarding complete." in message
    assert runtime.bot_state_store.get_onboarding(42) is None


@pytest.mark.asyncio
async def test_bot_service_photo_caption_updates_onboarding_state() -> None:
    runtime = FakeRuntime()
    service = GhostAttendBotService(runtime)  # type: ignore[arg-type]

    await service.handle_start(42)
    message = await service.handle_photo_message(
        42,
        Path("C:/tmp/fake.jpg"),
        caption="https://dys.mu.edu.tr/ seyfullahkorkmaz@posta.mu.edu.tr sifrem Seyfo46500. muglada yasiyorum",
    )

    draft = runtime.bot_state_store.get_onboarding(42)
    assert draft is not None
    assert draft.university_url == "https://dys.mu.edu.tr/"
    assert draft.email == "seyfullahkorkmaz@posta.mu.edu.tr"
    assert draft.password == "Seyfo46500."
    assert draft.timezone == "Europe/Istanbul"
    assert "ders programin" in message
