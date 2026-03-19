from dataclasses import dataclass, field

from app.domain.enums import OnboardingStep
from app.domain.schemas import ScheduleCandidate


@dataclass(slots=True)
class OnboardingDraft:
    telegram_id: int
    step: OnboardingStep = OnboardingStep.UNIVERSITY_URL
    university_url: str | None = None
    email: str | None = None
    password: str | None = None
    timezone: str | None = None
    schedule_candidate: ScheduleCandidate | None = None
    confirmation_received: bool = False
    notes: list[str] = field(default_factory=list)

    def is_ready_to_activate(self) -> bool:
        return all(
            [
                self.university_url,
                self.email,
                self.password,
                self.timezone,
                self.schedule_candidate is not None,
                self.confirmation_received,
            ]
        )
