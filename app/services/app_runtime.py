from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import timedelta
from typing import AsyncIterator

from app.agent.runtime import AgentRuntimeStore
from app.agent.tools_builder import build_agent_runtime
from app.bot.handlers import AgentCoordinator, BotStateStore, OnboardingCoordinator
from app.browser.runtime import BrowserContextManager, BrowserRuntime
from app.config import Settings
from app.container import AppContainer
from app.db.session import DatabaseManager
from app.services.deduplication import CommandDeduplicator
from app.services.metrics import MetricsCollector
from app.services.rate_limit import SlidingWindowRateLimiter
from app.services.task_queue import TaskQueueGateway
from app.scheduler.service import InMemorySchedulerBackend
from app.scheduler.loop import create_scheduler


@dataclass(slots=True)
class ApplicationRuntime:
    settings: Settings
    db: DatabaseManager
    bot_state_store: BotStateStore
    agent_runtime_store: AgentRuntimeStore
    browser_runtime: BrowserRuntime
    browser_context_manager: BrowserContextManager
    task_queue: TaskQueueGateway
    metrics: MetricsCollector
    rate_limiter: SlidingWindowRateLimiter
    command_deduplicator: CommandDeduplicator
    scheduler_backend: InMemorySchedulerBackend
    scheduler_instance: object | None
    registered_scheduler_job_ids: set[str]

    @classmethod
    def create(cls, settings: Settings) -> "ApplicationRuntime":
        browser_runtime = BrowserRuntime(
            headless=settings.browser_headless,
            screenshot_dir=settings.screenshot_dir,
        )
        return cls(
            settings=settings,
            db=DatabaseManager(settings),
            bot_state_store=BotStateStore(),
            agent_runtime_store=AgentRuntimeStore(),
            browser_runtime=browser_runtime,
            browser_context_manager=BrowserContextManager(runtime=browser_runtime),
            task_queue=TaskQueueGateway(),
            metrics=MetricsCollector(),
            rate_limiter=SlidingWindowRateLimiter(
                limit=settings.telegram_rate_limit_per_minute,
                window=timedelta(minutes=1),
            ),
            command_deduplicator=CommandDeduplicator(window=timedelta(seconds=30)),
            scheduler_backend=InMemorySchedulerBackend(),
            scheduler_instance=create_scheduler(),
            registered_scheduler_job_ids=set(),
        )

    @asynccontextmanager
    async def container(self) -> AsyncIterator[AppContainer]:
        async with self.db.session() as session:
            container = AppContainer.build(
                session,
                self.settings,
                browser_runtime=self.browser_runtime,
                browser_context_manager=self.browser_context_manager,
                task_queue=self.task_queue,
                metrics=self.metrics,
                rate_limiter=self.rate_limiter,
                command_deduplicator=self.command_deduplicator,
                scheduler_backend=self.scheduler_backend,
                scheduler_instance=self.scheduler_instance,
                registered_scheduler_job_ids=self.registered_scheduler_job_ids,
            )
            yield container
            await session.commit()

    async def close(self) -> None:
        await self.db.dispose()

    def build_onboarding_coordinator(self, container: AppContainer) -> OnboardingCoordinator:
        return OnboardingCoordinator(container.onboarding_service, self.bot_state_store)

    def build_agent_coordinator(self, container: AppContainer) -> AgentCoordinator:
        runtime = build_agent_runtime(container, store=self.agent_runtime_store)
        return AgentCoordinator(
            runtime_service=runtime,
            rate_limiter=container.rate_limiter,
            deduplicator=container.command_deduplicator,
        )
