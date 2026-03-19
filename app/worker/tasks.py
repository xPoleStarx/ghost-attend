from app.worker.celery_app import celery_app


@celery_app.task(name="notify_upcoming_class")
def notify_upcoming_class(user_id: int, course_id: int) -> dict[str, int]:
    return {"user_id": user_id, "course_id": course_id}


@celery_app.task(name="prepare_browser_session")
def prepare_browser_session(user_id: int, session_id: str, course_id: int | None = None) -> dict[str, str | int | None]:
    return {"user_id": user_id, "session_id": session_id, "course_id": course_id}


@celery_app.task(name="execute_join_flow")
def execute_join_flow(
    user_id: int, course_id: int, session_id: str | None = None
) -> dict[str, str | int | None]:
    return {"user_id": user_id, "course_id": course_id, "session_id": session_id}


@celery_app.task(name="execute_leave_flow")
def execute_leave_flow(
    user_id: int, session_id: str, course_id: int | None = None
) -> dict[str, str | int | None]:
    return {"user_id": user_id, "session_id": session_id, "course_id": course_id}


@celery_app.task(name="recover_active_session")
def recover_active_session(
    user_id: int, session_id: str, requires_login: bool = True
) -> dict[str, str | int | bool]:
    return {"user_id": user_id, "session_id": session_id, "requires_login": requires_login}
