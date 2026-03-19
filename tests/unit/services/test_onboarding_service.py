from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from app.config import Settings
from app.domain.enums import OnboardingStep
from app.security.crypto import CredentialCipher
from app.services.llm_onboarding import LLMOnboardingAssistant
from app.services.onboarding_service import OnboardingService
from app.services.schedule_ingestion import ScheduleIngestionService, StubScheduleImageExtractor
from app.services.schedule_parser import ScheduleParser
from app.services.timezone import TimezoneNormalizer


@dataclass
class FakeUser:
    id: int


@dataclass
class FakeSession:
    id: UUID


class FakeUserRepository:
    def __init__(self) -> None:
        self.created: list[dict[str, str | int]] = []

    async def create(
        self,
        *,
        telegram_id: int,
        email: object,
        password: object,
        timezone: str,
        university_url: str,
    ) -> FakeUser:
        self.created.append(
            {
                "telegram_id": telegram_id,
                "timezone": timezone,
                "university_url": university_url,
                "email": str(email),
                "password": str(password),
            }
        )
        return FakeUser(id=1)


class FakeCourseRepository:
    def __init__(self) -> None:
        self.rows: list[dict[str, str | None]] = []

    async def create_many(
        self,
        user_id: int,
        rows: list[dict[str, str | None]],
    ) -> list[dict[str, str | None]]:
        _ = user_id
        self.rows = rows
        return rows


class FakeSessionRepository:
    def __init__(self) -> None:
        self.created_count = 0

    async def create(self, user_id: int, metadata: dict[str, object] | None = None) -> FakeSession:
        _ = (user_id, metadata)
        self.created_count += 1
        return FakeSession(id=uuid4())


@pytest.fixture()
def onboarding_service(cipher: CredentialCipher) -> OnboardingService:
    return OnboardingService(
        user_repository=FakeUserRepository(),
        course_repository=FakeCourseRepository(),
        session_repository=FakeSessionRepository(),
        cipher=cipher,
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
    )


@pytest.mark.asyncio
async def test_onboarding_service_walks_text_flow_to_completion(
    onboarding_service: OnboardingService,
) -> None:
    draft, prompt = await onboarding_service.begin(telegram_id=99)

    assert prompt.step == OnboardingStep.UNIVERSITY_URL

    prompt = await onboarding_service.handle_text(
        draft,
        "DYS adresim dys.example.edu, mailim student@example.edu, sifrem pass123 ve saat dilimim Istanbul",
    )
    assert draft.university_url == "https://dys.example.edu"
    assert draft.email == "student@example.edu"
    assert draft.password == "pass123"
    assert draft.timezone == "Europe/Istanbul"
    assert prompt.step == OnboardingStep.SCHEDULE_INPUT

    prompt = await onboarding_service.handle_text(
        draft,
        "Kariyer planlama, her carsamba, 19.30da basliyor 20.00da bitiyor",
    )
    assert prompt.step == OnboardingStep.SCHEDULE_CONFIRMATION
    assert prompt.schedule_candidate is not None
    assert prompt.schedule_candidate.courses[0].day_of_week == "WEDNESDAY"

    prompt = await onboarding_service.handle_text(draft, "evet")
    assert prompt.is_complete is True
    assert draft.step == OnboardingStep.COMPLETED


@pytest.mark.asyncio
async def test_onboarding_service_empty_image_flow_requests_manual_schedule(
    onboarding_service: OnboardingService,
    tmp_path: Path,
) -> None:
    draft, _ = await onboarding_service.begin(telegram_id=100)
    draft.university_url = "https://dys.example.edu"
    draft.email = "student@example.edu"
    draft.password = "pass123"
    draft.timezone = "Europe/Istanbul"
    draft.step = OnboardingStep.SCHEDULE_INPUT

    image_path = tmp_path / "schedule.png"
    image_path.write_bytes(b"fake-image")

    prompt = await onboarding_service.handle_image(draft, image_path)

    assert prompt.step == OnboardingStep.SCHEDULE_INPUT
    assert prompt.schedule_candidate is not None
    assert prompt.schedule_candidate.warnings


@pytest.mark.asyncio
async def test_onboarding_service_blocks_conflicting_courses(
    onboarding_service: OnboardingService,
) -> None:
    draft, _ = await onboarding_service.begin(telegram_id=101)
    draft.university_url = "https://dys.example.edu"
    draft.email = "student@example.edu"
    draft.password = "pass123"
    draft.timezone = "Europe/Istanbul"
    draft.confirmation_received = True
    draft.schedule_candidate = ScheduleParser().parse_text(
        "\n".join(
            [
                "Kariyer Planlama | monday | 14:00 | 15:00 | https://example.com/a",
                "Yazilim | monday | 14:30 | 15:30 | https://example.com/b",
            ]
        )
    )
    draft.step = OnboardingStep.SCHEDULE_CONFIRMATION

    prompt = await onboarding_service.handle_text(draft, "YES")

    assert prompt.is_complete is False
    assert "Conflicting classes detected" in prompt.message
    assert draft.step == OnboardingStep.SCHEDULE_CONFIRMATION


@pytest.mark.asyncio
async def test_onboarding_service_accepts_embedded_timezone_phrase(
    onboarding_service: OnboardingService,
) -> None:
    draft, _ = await onboarding_service.begin(telegram_id=102)

    prompt = await onboarding_service.handle_text(
        draft,
        "dys.mu.edu.tr adresim, mailim student@example.edu, sifrem pass123, turkiye saatine gore yasiyorum",
    )

    assert draft.timezone == "Europe/Istanbul"
    assert prompt.step == OnboardingStep.SCHEDULE_INPUT


@pytest.mark.asyncio
async def test_onboarding_service_does_not_parse_timezone_as_schedule_after_empty_image(
    onboarding_service: OnboardingService,
    tmp_path: Path,
) -> None:
    draft, _ = await onboarding_service.begin(telegram_id=103)
    draft.university_url = "https://dys.example.edu"
    draft.email = "student@example.edu"
    draft.password = "pass123"

    image_path = tmp_path / "schedule-empty.png"
    image_path.write_bytes(b"fake-image")

    prompt = await onboarding_service.handle_image(draft, image_path)
    assert prompt.step == OnboardingStep.SCHEDULE_INPUT

    prompt = await onboarding_service.handle_text(draft, "Europe/Istanbul")

    assert draft.timezone == "Europe/Istanbul"
    assert prompt.step == OnboardingStep.SCHEDULE_INPUT
    if prompt.schedule_candidate is not None:
        assert "Could not parse line: Europe/Istanbul" not in prompt.schedule_candidate.warnings


@pytest.mark.asyncio
async def test_onboarding_service_applies_remove_commands_to_schedule_candidate(
    onboarding_service: OnboardingService,
) -> None:
    draft, _ = await onboarding_service.begin(telegram_id=104)
    draft.university_url = "https://dys.example.edu"
    draft.email = "student@example.edu"
    draft.password = "pass123"
    draft.timezone = "Europe/Istanbul"
    draft.schedule_candidate = ScheduleParser().parse_text(
        "\n".join(
            [
                "Senior Design Project II | friday | 08:30 | 09:15",
                "Almanca II | friday | 13:30 | 14:00",
                "Kariyer Planlama | tuesday | 11:10 | 11:40",
            ]
        )
    )
    draft.step = OnboardingStep.SCHEDULE_CONFIRMATION

    prompt = await onboarding_service.handle_text(
        draft,
        "Senior Design Project II ve Almanca II kaldir, bunlar online degil",
    )

    assert prompt.schedule_candidate is not None
    remaining_names = [course.name for course in prompt.schedule_candidate.courses]
    assert remaining_names == ["Kariyer Planlama"]
    assert any("removed" in warning for warning in prompt.schedule_candidate.warnings)


@pytest.mark.asyncio
async def test_onboarding_service_accepts_turkish_confirmation_word(
    onboarding_service: OnboardingService,
) -> None:
    draft, _ = await onboarding_service.begin(telegram_id=105)
    draft.university_url = "https://dys.example.edu"
    draft.email = "student@example.edu"
    draft.password = "pass123"
    draft.timezone = "Europe/Istanbul"
    draft.schedule_candidate = ScheduleParser().parse_text(
        "Kariyer Planlama | tuesday | 11:10 | 11:40"
    )
    draft.step = OnboardingStep.SCHEDULE_CONFIRMATION

    prompt = await onboarding_service.handle_text(draft, "onaylıyorum")

    assert prompt.is_complete is True
    assert draft.step == OnboardingStep.COMPLETED
