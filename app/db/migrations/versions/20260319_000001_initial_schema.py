"""Initial schema."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260319_000001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("telegram_id", sa.Integer(), nullable=False),
        sa.Column("email_encrypted", sa.Text(), nullable=False),
        sa.Column("password_encrypted", sa.Text(), nullable=False),
        sa.Column("key_version", sa.String(length=32), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("university_url", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_users_telegram_id", "users", ["telegram_id"], unique=True)

    op.create_table(
        "courses",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("start_day_of_week_utc", sa.String(length=16), nullable=False),
        sa.Column("end_day_of_week_utc", sa.String(length=16), nullable=False),
        sa.Column("start_time_utc", sa.String(length=8), nullable=False),
        sa.Column("end_time_utc", sa.String(length=8), nullable=False),
        sa.Column("teams_link", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_courses_user_id", "courses", ["user_id"], unique=False)

    op.create_table(
        "sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("session_metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"], unique=False)

    op.create_table(
        "scheduler_jobs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("course_id", sa.Integer(), sa.ForeignKey("courses.id"), nullable=False),
        sa.Column("job_type", sa.String(length=32), nullable=False),
        sa.Column("apscheduler_job_id", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_index("ix_scheduler_jobs_user_id", "scheduler_jobs", ["user_id"], unique=False)
    op.create_index("ix_scheduler_jobs_course_id", "scheduler_jobs", ["course_id"], unique=False)
    op.create_index("ix_scheduler_jobs_job_type", "scheduler_jobs", ["job_type"], unique=False)
    op.create_unique_constraint(
        "uq_scheduler_jobs_apscheduler_job_id",
        "scheduler_jobs",
        ["apscheduler_job_id"],
    )

    op.create_table(
        "human_input_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sessions.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("tool_name", sa.String(length=128), nullable=False),
        sa.Column("reason", sa.String(length=128), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("screenshot_path", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_human_input_requests_session_id", "human_input_requests", ["session_id"], unique=False)
    op.create_index("ix_human_input_requests_user_id", "human_input_requests", ["user_id"], unique=False)
    op.create_index("ix_human_input_requests_status", "human_input_requests", ["status"], unique=False)

    op.create_table(
        "audit_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sessions.id"), nullable=True),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audit_events_user_id", "audit_events", ["user_id"], unique=False)
    op.create_index("ix_audit_events_session_id", "audit_events", ["session_id"], unique=False)
    op.create_index("ix_audit_events_event_type", "audit_events", ["event_type"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_audit_events_event_type", table_name="audit_events")
    op.drop_index("ix_audit_events_session_id", table_name="audit_events")
    op.drop_index("ix_audit_events_user_id", table_name="audit_events")
    op.drop_table("audit_events")

    op.drop_index("ix_human_input_requests_status", table_name="human_input_requests")
    op.drop_index("ix_human_input_requests_user_id", table_name="human_input_requests")
    op.drop_index("ix_human_input_requests_session_id", table_name="human_input_requests")
    op.drop_table("human_input_requests")

    op.drop_constraint("uq_scheduler_jobs_apscheduler_job_id", "scheduler_jobs", type_="unique")
    op.drop_index("ix_scheduler_jobs_job_type", table_name="scheduler_jobs")
    op.drop_index("ix_scheduler_jobs_course_id", table_name="scheduler_jobs")
    op.drop_index("ix_scheduler_jobs_user_id", table_name="scheduler_jobs")
    op.drop_table("scheduler_jobs")

    op.drop_index("ix_sessions_user_id", table_name="sessions")
    op.drop_table("sessions")

    op.drop_index("ix_courses_user_id", table_name="courses")
    op.drop_table("courses")

    op.drop_index("ix_users_telegram_id", table_name="users")
    op.drop_table("users")
