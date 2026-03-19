from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.browser.adapters import GenericDysAdapter
from app.browser.runtime import BrowserContextManager, BrowserRuntime
from app.config import Settings, get_settings
from app.repos.audit import AuditRepository
from app.repos.courses import CourseRepository
from app.repos.human_input import HumanInputRepository
from app.repos.scheduler_jobs import SchedulerJobRepository
from app.repos.sessions import SessionRepository
from app.repos.users import UserRepository
from app.security.crypto import CredentialCipher
from app.services.conflicts import ScheduleConflictDetector
from app.services.deduplication import CommandDeduplicator
from app.services.metrics import MetricsCollector
from app.services.onboarding_service import OnboardingService
from app.services.observability import ObservabilityService
from app.services.operator_snapshot import OperatorSnapshotService
from app.services.rate_limit import SlidingWindowRateLimiter
from app.services.recovery import RecoveryService
from app.services.llm_onboarding import LLMOnboardingAssistant
from app.services.schedule_ingestion import LLMScheduleImageExtractor, ScheduleIngestionService
from app.services.schedule_parser import ScheduleParser
from app.services.task_queue import TaskQueueGateway
from app.services.timezone import TimezoneNormalizer
from app.scheduler.bootstrap import SchedulerBootstrapService
from app.scheduler.loop import APSchedulerLoop
from app.scheduler.planner import SchedulerPlanner
from app.scheduler.recovery import RecoveryCoordinator
from app.scheduler.service import InMemorySchedulerBackend, SchedulingService


@dataclass(slots=True)
class AppContainer:
    settings: Settings
    db_session: AsyncSession
    cipher: CredentialCipher
    schedule_parser: ScheduleParser
    browser_runtime: BrowserRuntime
    browser_context_manager: BrowserContextManager
    university_adapter: GenericDysAdapter
    schedule_ingestion: ScheduleIngestionService
    timezone_normalizer: TimezoneNormalizer
    onboarding_service: OnboardingService
    scheduling_service: SchedulingService
    scheduler_loop: APSchedulerLoop
    scheduler_bootstrap_service: SchedulerBootstrapService
    recovery_service: RecoveryService
    recovery_coordinator: RecoveryCoordinator
    task_queue: TaskQueueGateway
    metrics: MetricsCollector
    observability_service: ObservabilityService
    operator_snapshot_service: OperatorSnapshotService
    rate_limiter: SlidingWindowRateLimiter
    command_deduplicator: CommandDeduplicator
    conflict_detector: ScheduleConflictDetector
    user_repository: UserRepository
    course_repository: CourseRepository
    session_repository: SessionRepository
    scheduler_job_repository: SchedulerJobRepository
    human_input_repository: HumanInputRepository
    audit_repository: AuditRepository

    @classmethod
    def build(
        cls,
        db_session: AsyncSession,
        settings: Settings | None = None,
        *,
        browser_runtime: BrowserRuntime | None = None,
        browser_context_manager: BrowserContextManager | None = None,
        task_queue: TaskQueueGateway | None = None,
        metrics: MetricsCollector | None = None,
        rate_limiter: SlidingWindowRateLimiter | None = None,
        command_deduplicator: CommandDeduplicator | None = None,
        scheduler_backend: InMemorySchedulerBackend | None = None,
        scheduler_instance: object | None = None,
        registered_scheduler_job_ids: set[str] | None = None,
    ) -> "AppContainer":
        resolved_settings = settings or get_settings()
        resolved_browser_runtime = browser_runtime or BrowserRuntime(
            headless=resolved_settings.browser_headless,
            screenshot_dir=resolved_settings.screenshot_dir,
        )
        resolved_browser_context_manager = browser_context_manager or BrowserContextManager(
            runtime=resolved_browser_runtime
        )
        cipher = CredentialCipher(
            raw_secret=resolved_settings.secret_key.get_secret_value(),
            key_version=resolved_settings.secret_key_version,
        )
        schedule_parser = ScheduleParser()
        schedule_ingestion = ScheduleIngestionService(
            parser=schedule_parser,
            image_extractor=LLMScheduleImageExtractor(resolved_settings),
        )
        timezone_normalizer = TimezoneNormalizer()
        user_repository = UserRepository(db_session)
        course_repository = CourseRepository(db_session)
        session_repository = SessionRepository(db_session)
        scheduler_job_repository = SchedulerJobRepository(db_session)
        human_input_repository = HumanInputRepository(db_session)
        audit_repository = AuditRepository(db_session)
        resolved_task_queue = task_queue or TaskQueueGateway()
        resolved_metrics = metrics or MetricsCollector()
        observability_service = ObservabilityService(
            audit_repository=audit_repository, metrics=resolved_metrics
        )
        resolved_rate_limiter = rate_limiter or SlidingWindowRateLimiter(
            limit=resolved_settings.telegram_rate_limit_per_minute,
            window=timedelta(minutes=1),
        )
        resolved_command_deduplicator = command_deduplicator or CommandDeduplicator(
            window=timedelta(seconds=30)
        )
        conflict_detector = ScheduleConflictDetector()
        llm_assistant = LLMOnboardingAssistant(resolved_settings)
        recovery_service = RecoveryService()
        resolved_scheduler_backend = scheduler_backend or InMemorySchedulerBackend()
        scheduling_service = SchedulingService(
            planner=SchedulerPlanner(),
            backend=resolved_scheduler_backend,
            task_queue=resolved_task_queue,
            scheduler_job_repository=scheduler_job_repository,
        )
        scheduler_loop = APSchedulerLoop(
            scheduling_service=scheduling_service,
            scheduler=scheduler_instance,
            registered_job_ids=(
                registered_scheduler_job_ids if registered_scheduler_job_ids is not None else set()
            ),
        )
        return cls(
            settings=resolved_settings,
            db_session=db_session,
            cipher=cipher,
            schedule_parser=schedule_parser,
            browser_runtime=resolved_browser_runtime,
            browser_context_manager=resolved_browser_context_manager,
            university_adapter=GenericDysAdapter(),
            schedule_ingestion=schedule_ingestion,
            timezone_normalizer=timezone_normalizer,
            onboarding_service=OnboardingService(
                user_repository=user_repository,
                course_repository=course_repository,
                session_repository=session_repository,
                cipher=cipher,
                schedule_ingestion=schedule_ingestion,
                timezone_normalizer=timezone_normalizer,
                llm_assistant=llm_assistant,
                conflict_detector=conflict_detector,
            ),
            scheduling_service=scheduling_service,
            scheduler_loop=scheduler_loop,
            scheduler_bootstrap_service=SchedulerBootstrapService(
                course_repository=course_repository,
                scheduling_service=scheduling_service,
                scheduler_loop=scheduler_loop,
            ),
            recovery_service=recovery_service,
            recovery_coordinator=RecoveryCoordinator(session_repository, recovery_service),
            task_queue=resolved_task_queue,
            metrics=resolved_metrics,
            observability_service=observability_service,
            operator_snapshot_service=OperatorSnapshotService(
                browser_contexts=resolved_browser_context_manager,
                task_queue=resolved_task_queue,
                metrics=resolved_metrics,
            ),
            rate_limiter=resolved_rate_limiter,
            command_deduplicator=resolved_command_deduplicator,
            conflict_detector=conflict_detector,
            user_repository=user_repository,
            course_repository=course_repository,
            session_repository=session_repository,
            scheduler_job_repository=scheduler_job_repository,
            human_input_repository=human_input_repository,
            audit_repository=audit_repository,
        )
