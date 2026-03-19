import pytest

from app.config import Settings
from app.security.crypto import CredentialCipher
from app.services.schedule_parser import ScheduleParser


@pytest.fixture()
def settings() -> Settings:
    return Settings(
        DATABASE_URL="sqlite+aiosqlite:///:memory:",
        REDIS_URL="redis://localhost:6379/0",
        SECRET_KEY="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
    )


@pytest.fixture()
def cipher(settings: Settings) -> CredentialCipher:
    return CredentialCipher(
        raw_secret=settings.secret_key.get_secret_value(),
        key_version=settings.secret_key_version,
    )


@pytest.fixture()
def schedule_parser() -> ScheduleParser:
    return ScheduleParser()
