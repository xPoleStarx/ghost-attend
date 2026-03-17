"""
GhostAttend — FSM State Tanımları

Telegram bot ConversationHandler state'leri.
architecture.md Section 6.1
"""

from enum import IntEnum


class OnboardingState(IntEnum):
    """Onboarding (ilk kurulum) zinciri state'leri."""

    WELCOME = 1
    ASK_DYS_URL = 2
    ASK_CREDENTIAL_TYPE = 3   # unified mi, ayrı mı
    ASK_DYS_EMAIL = 4
    ASK_DYS_PASSWORD = 5
    ASK_TEAMS_EMAIL = 6
    ASK_TEAMS_PASSWORD = 7
    VERIFY_CREDENTIALS = 8
    ASK_SCHEDULE_PHOTO = 9
    CONFIRM_COURSES = 10
    SETUP_COMPLETE = 11
    CHAT_ONLINE_COURSES = 12  # LLM chatbot ile online ders düzenleme


class SessionState(IntEnum):
    """Aktif oturum yönetimi state'leri."""

    IDLE = 20
    MFA_WAITING = 21   # Kullanıcıdan MFA kodu bekleniyor
    RUNNING = 22
    CANCELLING = 23
