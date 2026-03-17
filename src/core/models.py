"""
GhostAttend — Pydantic Domain Modelleri

API ve servisler arası veri taşıma için kullanılan modeller.
ORM modelleri src/db/models.py'de yaşar; bunlar domain/DTO modeldir.
"""

from datetime import time
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


# ── Vision Parse Modelleri ──

class ParsedCourse(BaseModel):
    """Vision LLM'in ders programından parse ettiği tek bir ders."""

    ders_adi: str
    gun: Literal["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
    baslangic_saati: str  # "HH:MM" formatı
    bitis_saati: str  # "HH:MM" formatı
    ogretim_uyesi: str | None = None
    platform: Literal["teams", "zoom", "meet", "unknown"] = "unknown"
    online_mi: bool | None = None  # None = belirsiz
    guvven_skoru: float = Field(ge=0.0, le=1.0, description="LLM'in güven skoru")


class ScheduleParseResult(BaseModel):
    """Vision LLM'in tüm parse sonucu."""

    courses: list[ParsedCourse]
    raw_text: str  # LLM'in okuduğu ham metin
    parse_warnings: list[str] = Field(default_factory=list)


# ── Course Yönetim Modelleri ──

class CourseInfo(BaseModel):
    """Kaydedilmiş ders bilgisi DTO'su."""

    id: UUID | None = None
    name: str
    instructor: str | None = None
    platform: str = "teams"
    day_of_week: int = Field(ge=0, le=6)  # 0=Pazartesi, 6=Pazar
    start_time: time
    end_time: time
    direct_url: str | None = None
    dys_search_hint: str | None = None
    is_active: bool = True
    semester: str | None = None


# ── Session Modelleri ──

class SessionStatus(BaseModel):
    """Aktif oturum durumu DTO'su."""

    session_id: UUID
    course_name: str
    status: Literal["pending", "running", "joined", "failed", "cancelled", "completed"]
    retry_count: int = 0
    failure_reason: str | None = None


# ── Credential Modelleri ──

class CredentialInput(BaseModel):
    """Kullanıcının girdiği credential bilgisi."""

    dys_url: str
    email: str
    password: str
    credential_type: Literal["unified", "dys", "teams"] = "unified"


# ── Agent Checkpoint Modelleri ──

class CheckpointEvent(BaseModel):
    """Agent'ın gönderdiği checkpoint bilgisi."""

    checkpoint_name: str
    screenshot_path: str | None = None
    message: str = ""
    metadata: dict = Field(default_factory=dict)
