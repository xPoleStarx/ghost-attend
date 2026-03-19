from __future__ import annotations

from dataclasses import dataclass

from app.bot.application import TelegramApplicationService
from app.config import Settings
from app.services.app_runtime import ApplicationRuntime
from app.telemetry.logging import get_logger


@dataclass(slots=True)
class GhostAttendApplication:
    settings: Settings
    runtime: ApplicationRuntime
    telegram_service: TelegramApplicationService

    @classmethod
    def build(cls, settings: Settings) -> "GhostAttendApplication":
        runtime = ApplicationRuntime.create(settings)
        telegram_service = TelegramApplicationService(runtime)
        return cls(settings=settings, runtime=runtime, telegram_service=telegram_service)

    async def startup(self) -> dict[str, object]:
        log = get_logger(component="app_startup")
        async with self.runtime.container() as container:
            try:
                await container.scheduler_loop.start()
                bootstrap_result = await container.scheduler_bootstrap_service.bootstrap_all_active_courses()
                bootstrap = await container.recovery_coordinator.list_recovery_plans()
                snapshot = await container.operator_snapshot_service.snapshot()
            except Exception as exc:  # noqa: BLE001
                log.warning("app.startup_partial", error=str(exc))
                return {
                    "scheduled_course_count": 0,
                    "scheduled_job_count": 0,
                    "recovery_plan_count": 0,
                    "active_context_count": 0,
                }
            log.info(
                "app.startup",
                scheduled_course_count=bootstrap_result.scheduled_course_count,
                scheduled_job_count=bootstrap_result.scheduled_job_count,
                recovery_plan_count=len(bootstrap),
                active_context_count=snapshot["active_context_count"],
            )
            return {
                "scheduled_course_count": bootstrap_result.scheduled_course_count,
                "scheduled_job_count": bootstrap_result.scheduled_job_count,
                "recovery_plan_count": len(bootstrap),
                "active_context_count": snapshot["active_context_count"],
            }

    async def shutdown(self) -> None:
        async with self.runtime.container() as container:
            await container.scheduler_loop.stop()
        await self.runtime.close()
