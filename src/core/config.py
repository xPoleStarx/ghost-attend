"""
GhostAttend — Application Configuration

Pydantic Settings ile environment variable yönetimi.
Tüm config değerleri .env dosyasından veya environment'tan okunur.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application-wide settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ── Uygulama ──
    ENVIRONMENT: str = "production"
    LOG_LEVEL: str = "INFO"

    # ── Telegram ──
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_WEBHOOK_URL: str = ""
    TELEGRAM_WEBHOOK_SECRET: str = ""

    # ── LLM ──
    ANTHROPIC_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    GOOGLE_API_KEY: str = ""
    AGENT_LLM_PROVIDER: str = "google"  # google | openai | anthropic
    AGENT_LLM_MODEL: str = "gemini-3.1-flash-lite"
    VISION_LLM_MODEL: str = "gemini-3.1-flash-lite"

    # ── Veritabanı ──
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost/ghostattend"

    # ── Redis ──
    REDIS_URL: str = "redis://localhost:6379/0"

    # ── Güvenlik ──
    MASTER_ENCRYPTION_KEY: str = ""

    # ── Agent ──
    BROWSER_HEADLESS: bool = True
    AGENT_TIMEOUT_SECONDS: int = 3600
    AGENT_MAX_RETRY: int = 3
    MEETING_START_OFFSET_MINUTES: int = 5

    # ── Screenshot ──
    SCREENSHOT_STORAGE: str = "local"  # local | s3
    SCREENSHOT_DIR: str = "/app/screenshots"

    @property
    def is_development(self) -> bool:
        return self.ENVIRONMENT == "development"

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    @property
    def is_test(self) -> bool:
        return self.ENVIRONMENT == "test"


settings = Settings()
