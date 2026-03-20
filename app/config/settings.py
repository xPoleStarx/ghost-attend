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

    # browser-use: çapraz alan gezinmede hazırlık bekleme (kütüphane varsayılanı 8 sn; DDG vb. için artırılır)
    browser_nav_readiness_timeout: float = Field(default=18.0, ge=3.0, le=120.0)
    # False: OOPIF/reklam iframe'lerinde DOM/CDP yarışı azalabilir; bazı sitelerde içerik eksik kalabilir
    browser_cross_origin_iframes: bool = Field(default=True)
    browser_minimum_wait_page_load_time: float = Field(default=0.28, ge=0.0, le=5.0)
    browser_wait_for_network_idle_page_load_time: float = Field(default=0.55, ge=0.0, le=10.0)
    browser_wait_between_actions: float = Field(default=0.15, ge=0.0, le=5.0)

    log_redact_telegram_token: bool = Field(default=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
