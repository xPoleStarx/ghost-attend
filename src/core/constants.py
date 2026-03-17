"""
GhostAttend — Sabitler

LLM modelleri, timeout, retry ve diğer proje geneli sabitler.
Hardcode değerler burada yaşar; gerektiğinde config'den override edilir.
"""

from typing import Final

# ── LLM Model Tanımları ──
LLM_MODELS: Final[dict[str, dict[str, str]]] = {
    "google": {
        "agent": "gemini-3.1-flash-lite-preview",
        "vision": "gemini-3.1-flash-lite-preview",
    },
    "openai": {
        "agent": "gpt-4o-mini",
        "vision": "gpt-4o-mini",
    },
    "anthropic": {
        "agent": "claude-3-5-haiku-20241022",
        "vision": "claude-3-5-haiku-20241022",
    },
}

# ── Gün Haritası (APScheduler için) ──
DAYS_MAP: Final[dict[int, str]] = {
    0: "mon",
    1: "tue",
    2: "wed",
    3: "thu",
    4: "fri",
    5: "sat",
    6: "sun",
}

DAYS_TR: Final[dict[str, int]] = {
    "Pazartesi": 0,
    "Salı": 1,
    "Çarşamba": 2,
    "Perşembe": 3,
    "Cuma": 4,
    "Cumartesi": 5,
    "Pazar": 6,
}

# ── Timeout & Retry ──
AGENT_TIMEOUT_SECONDS: Final[int] = 3600  # 1 saat max ders süresi
AGENT_MAX_RETRY: Final[int] = 3
RETRY_DELAY_SECONDS: Final[int] = 120  # Retry arası bekleme
MEETING_START_OFFSET_MINUTES: Final[int] = 5  # Dersten kaç dk önce başla
MEETING_WAIT_TIMEOUT_MINUTES: Final[int] = 10  # Hoca başlatmadıysa max bekleme
MEETING_WAIT_INTERVAL_SECONDS: Final[int] = 120  # Her 2dk'da bir yenile

# ── MFA Timeout ──
MFA_SMS_TIMEOUT_SECONDS: Final[int] = 60
MFA_PUSH_TIMEOUT_SECONDS: Final[int] = 120

# ── Cookie ──
COOKIE_EXPIRY_DAYS: Final[int] = 85  # 90 gün - 5 gün marj
COOKIE_WARNING_DAYS: Final[int] = 7  # Expire'dan 7 gün önce uyarı

# ── Credential Silme ──
PASSWORD_MESSAGE_DELETE_DELAY: Final[int] = 1  # Şifre mesajını kaç sn sonra sil

# ── Agent Checkpoint İsimleri ──
CHECKPOINT_DYS_LOGIN: Final[str] = "dys_login"
CHECKPOINT_LINK_FOUND: Final[str] = "ders_link_bulundu"
CHECKPOINT_JOINED: Final[str] = "derse_girildi"
CHECKPOINT_COMPLETED: Final[str] = "ders_tamamlandi"

# ── Redis Key Prefix'leri ──
REDIS_PREFIX_MFA: Final[str] = "mfa:"
REDIS_PREFIX_CANCEL: Final[str] = "cancel:"
REDIS_PREFIX_SESSION: Final[str] = "session:"

# ── Platform Tanımları ──
SUPPORTED_PLATFORMS: Final[list[str]] = ["teams", "zoom", "meet", "unknown"]

# ── Agent Hata Kodları ──
ERROR_DYS_LOGIN_FAILED: Final[str] = "DYS_LOGIN_FAILED"
ERROR_LINK_NOT_FOUND: Final[str] = "LINK_NOT_FOUND"
ERROR_MFA_REQUIRED: Final[str] = "MFA_REQUIRED"
ERROR_JOIN_FAILED: Final[str] = "JOIN_FAILED"
ERROR_PAGE_FROZEN: Final[str] = "PAGE_FROZEN"
ERROR_MEETING_NOT_STARTED: Final[str] = "MEETING_NOT_STARTED"
ERROR_MAX_RETRY_EXCEEDED: Final[str] = "MAX_RETRY_EXCEEDED"
