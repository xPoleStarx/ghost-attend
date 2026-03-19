from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    telegram_bot_token: str = Field(..., description="BotFather token (env: TELEGRAM_BOT_TOKEN)")
    google_api_key: str = Field(..., description="Gemini API key (env: GOOGLE_API_KEY)")

    gemini_model: str = Field(default="gemini-2.5-flash")
    playwright_headless: bool = Field(default=False)
    checkpoint_path: str = Field(default="./data/checkpoints.db")

    browser_max_steps: int = Field(default=35, ge=1, le=200)
    browser_step_timeout: int = Field(default=180, ge=10, le=600)


@lru_cache
def get_settings() -> Settings:
    return Settings()
