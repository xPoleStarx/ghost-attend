from dataclasses import dataclass, field
from pathlib import Path

from app.agent.runtime import AgentRuntimeService
from app.domain.schemas import OnboardingPrompt
from app.services.deduplication import CommandDeduplicator
from app.services.onboarding import OnboardingDraft
from app.services.onboarding_service import OnboardingService
from app.services.rate_limit import SlidingWindowRateLimiter


@dataclass(slots=True)
class BotStateStore:
    onboarding_drafts: dict[int, OnboardingDraft] = field(default_factory=dict)

    def start_onboarding(self, telegram_id: int) -> OnboardingDraft:
        draft = OnboardingDraft(telegram_id=telegram_id)
        self.onboarding_drafts[telegram_id] = draft
        return draft

    def get_onboarding(self, telegram_id: int) -> OnboardingDraft | None:
        return self.onboarding_drafts.get(telegram_id)

    def clear_onboarding(self, telegram_id: int) -> None:
        self.onboarding_drafts.pop(telegram_id, None)


class OnboardingCoordinator:
    def __init__(self, onboarding_service: OnboardingService, state_store: BotStateStore) -> None:
        self.onboarding_service = onboarding_service
        self.state_store = state_store

    async def begin(self, telegram_id: int) -> OnboardingPrompt:
        draft, prompt = await self.onboarding_service.begin(telegram_id)
        self.state_store.onboarding_drafts[telegram_id] = draft
        return prompt

    async def handle_text(self, telegram_id: int, text: str) -> OnboardingPrompt:
        draft = self.state_store.get_onboarding(telegram_id)
        if draft is None:
            return await self.begin(telegram_id)
        prompt = await self.onboarding_service.handle_text(draft, text)
        return prompt

    async def handle_image(self, telegram_id: int, image_path: Path) -> OnboardingPrompt:
        draft = self.state_store.get_onboarding(telegram_id)
        if draft is None:
            return await self.begin(telegram_id)
        return await self.onboarding_service.handle_image(draft, image_path)


class AgentCoordinator:
    def __init__(
        self,
        runtime_service: AgentRuntimeService,
        rate_limiter: SlidingWindowRateLimiter | None = None,
        deduplicator: CommandDeduplicator | None = None,
    ) -> None:
        self.runtime_service = runtime_service
        self.rate_limiter = rate_limiter
        self.deduplicator = deduplicator

    async def handle_message(
        self,
        *,
        session_id: str,
        user_id: int,
        user_timezone: str,
        message: str,
        schedule: list[dict[str, object]] | None = None,
    ) -> str:
        if self.rate_limiter is not None and not self.rate_limiter.allow(user_id):
            return "Rate limit exceeded. Please wait a bit before sending another command."
        if self.deduplicator is not None and self.deduplicator.seen_recently(user_id, message.strip().lower()):
            return "Duplicate command ignored because it was received too recently."
        state = await self.runtime_service.handle_message(
            session_id=session_id,
            user_id=user_id,
            user_timezone=user_timezone,
            message=message,
            schedule=schedule,
        )
        return str(state.get("response", ""))
