from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    llm_provider: str = Field(default="gemini", alias="LLM_PROVIDER")
    llm_model: str = Field(default="gemini-2.5-flash-lite-preview", alias="LLM_MODEL")
    google_api_key: SecretStr | None = Field(default=None, alias="GOOGLE_API_KEY")
    openai_api_key: SecretStr | None = Field(default=None, alias="OPENAI_API_KEY")
    anthropic_api_key: SecretStr | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    telegram_bot_token: SecretStr | None = Field(default=None, alias="TELEGRAM_BOT_TOKEN")
    database_url: str = Field(alias="DATABASE_URL")
    redis_url: str = Field(alias="REDIS_URL")
    secret_key: SecretStr = Field(alias="SECRET_KEY")
    secret_key_version: str = Field(default="v1", alias="SECRET_KEY_VERSION")
    browser_headless: bool = Field(default=True, alias="BROWSER_HEADLESS")
    playwright_executable_path: Path | None = Field(
        default=None, alias="PLAYWRIGHT_EXECUTABLE_PATH"
    )
    page_timeout_ms: int = Field(default=30000, alias="PAGE_TIMEOUT")
    max_retries: int = Field(default=3, alias="MAX_RETRIES")
    max_tool_timeout_seconds: int = Field(default=60, alias="MAX_TOOL_TIMEOUT")
    screenshot_dir: Path = Field(default=Path("/tmp/ghost-attend/screenshots"), alias="SCREENSHOT_DIR")
    worker_concurrency: int = Field(default=4, alias="WORKER_CONCURRENCY")
    default_timezone: str = Field(default="Europe/Istanbul", alias="DEFAULT_TIMEZONE")
    login_failure_cooldown_seconds: int = Field(default=300, alias="LOGIN_FAILURE_COOLDOWN_SECONDS")
    human_input_timeout_seconds: int = Field(default=300, alias="HUMAN_INPUT_TIMEOUT_SECONDS")
    telegram_rate_limit_per_minute: int = Field(default=20, alias="TELEGRAM_RATE_LIMIT_PER_MINUTE")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
