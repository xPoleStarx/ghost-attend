"""GhostAttend FSM state definitions."""

from enum import IntEnum


class OnboardingState(IntEnum):
    """First-time setup states."""

    WELCOME = 1
    ASK_DYS_URL = 2
    ASK_CREDENTIAL_TYPE = 3
    ASK_DYS_EMAIL = 4
    ASK_DYS_PASSWORD = 5
    ASK_TEAMS_EMAIL = 6
    ASK_TEAMS_PASSWORD = 7
    VERIFY_CREDENTIALS = 8
    ASK_TIMEZONE = 9
    ASK_SCHEDULE_PHOTO = 10
    CONFIRM_COURSES = 11
    SETUP_COMPLETE = 12
    CHAT_ONLINE_COURSES = 13


class SessionState(IntEnum):
    """Legacy session states still used by handlers."""

    IDLE = 20
    MFA_WAITING = 21
    RUNNING = 22
    CANCELLING = 23


class RuntimeLifecycleState(IntEnum):
    """High-level runtime safety boundaries."""

    ONBOARDING = 30
    READY = 31
    SESSION_STARTING = 32
    SESSION_ACTIVE = 33
    MFA_WAITING = 34
    SESSION_BLOCKED = 35
    SESSION_CANCELLING = 36
    ERROR_RECOVERY = 37
