"""
GhostAttend — SQLAlchemy ORM Modelleri

architecture.md Section 5 veritabanı şemasına birebir karşılık gelir.
6 tablo: users, credentials, courses, agent_sessions, session_checkpoints, notifications
"""

import uuid
from datetime import datetime, time

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    LargeBinary,
    SmallInteger,
    String,
    Text,
    Time,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    """ORM base class."""
    pass


class User(Base):
    """Telegram kullanıcısı."""
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)  # Telegram user_id
    username: Mapped[str | None] = mapped_column(String(64))
    first_name: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    onboarding_step: Mapped[str] = mapped_column(String(32), default="start")
    timezone: Mapped[str] = mapped_column(String(64), default="Europe/Istanbul")

    # Relationships
    credentials: Mapped[list["Credential"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    courses: Mapped[list["Course"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    sessions: Mapped[list["AgentSession"]] = relationship(back_populates="user")
    notifications: Mapped[list["Notification"]] = relationship(back_populates="user")


class Credential(Base):
    """Şifreli credential deposu."""
    __tablename__ = "credentials"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    type: Mapped[str] = mapped_column(String(16), nullable=False)  # 'dys' | 'teams' | 'unified'
    dys_url: Mapped[str | None] = mapped_column(Text)
    email_enc: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)  # Fernet encrypted
    password_enc: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)  # Fernet encrypted
    cookie_enc: Mapped[bytes | None] = mapped_column(LargeBinary)  # Encrypted session cookies
    cookie_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_verified: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    user: Mapped["User"] = relationship(back_populates="credentials")

    __table_args__ = (
        Index("uq_user_type", "user_id", "type", unique=True),
    )


class Course(Base):
    """Kaydedilmiş dersler."""
    __tablename__ = "courses"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    instructor: Mapped[str | None] = mapped_column(String(256))
    platform: Mapped[str] = mapped_column(String(32), default="teams")
    day_of_week: Mapped[int] = mapped_column(SmallInteger, nullable=False)  # 0=Pazartesi, 6=Pazar
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    direct_url: Mapped[str | None] = mapped_column(Text)
    dys_search_hint: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_online: Mapped[bool | None] = mapped_column(Boolean, nullable=True, default=None)
    semester: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    user: Mapped["User"] = relationship(back_populates="courses")
    sessions: Mapped[list["AgentSession"]] = relationship(back_populates="course")

    __table_args__ = (
        Index("idx_courses_user_active", "user_id", "is_active"),
    )


class AgentSession(Base):
    """Agent oturumları — her ders girişi bir session oluşturur."""
    __tablename__ = "agent_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    course_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("courses.id"), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending"
    )  # pending | running | joined | failed | cancelled | completed
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    joined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_reason: Mapped[str | None] = mapped_column(Text)
    retry_count: Mapped[int] = mapped_column(SmallInteger, default=0)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    user: Mapped["User"] = relationship(back_populates="sessions")
    course: Mapped["Course"] = relationship(back_populates="sessions")
    checkpoints: Mapped[list["SessionCheckpoint"]] = relationship(back_populates="session", cascade="all, delete-orphan")
    notifications: Mapped[list["Notification"]] = relationship(back_populates="session")

    __table_args__ = (
        Index("idx_sessions_user_status", "user_id", "status"),
        Index("idx_sessions_created", "created_at"),
    )


class SessionCheckpoint(Base):
    """Checkpoint (screenshot) kayıtları."""
    __tablename__ = "session_checkpoints"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_sessions.id", ondelete="CASCADE"), nullable=False
    )
    checkpoint_name: Mapped[str] = mapped_column(String(64), nullable=False)
    screenshot_path: Mapped[str | None] = mapped_column(Text)
    telegram_file_id: Mapped[str | None] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)

    # Relationships
    session: Mapped["AgentSession"] = relationship(back_populates="checkpoints")


class Notification(Base):
    """Bildirim logu."""
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    session_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("agent_sessions.id"))
    type: Mapped[str | None] = mapped_column(String(32))  # 'screenshot' | 'error' | 'mfa_request' | 'completed'
    message: Mapped[str | None] = mapped_column(Text)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)

    # Relationships
    user: Mapped["User"] = relationship(back_populates="notifications")
    session: Mapped["AgentSession | None"] = relationship(back_populates="notifications")
