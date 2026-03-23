from functools import lru_cache
from typing import Literal

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

    # browser-use: CDP lifecycle hazırlık süresi (domcontentloaded ile genelde 8–12 sn yeter; ağır siteler için artırın)
    browser_nav_readiness_timeout: float = Field(default=12.0, ge=3.0, le=120.0)
    # Aynı site içi navigate (ör. youtube.com → youtube.com): eski 3 sn yerine — SPA’lar için tam readiness ile hizalı tutun
    browser_same_origin_nav_timeout: float = Field(default=12.0, ge=3.0, le=120.0)
    # Bu hostlar (virgülle) her zaman tam readiness süresi kullanır; youtube.com aynı-origin kısayoluna girmez
    browser_nav_always_full_readiness_hosts: str = Field(
        default="youtube.com,www.youtube.com,m.youtube.com",
        description="env: BROWSER_NAV_ALWAYS_FULL_READINESS_HOSTS",
    )
    # navigate_to / NavigateToUrlEvent → _navigate_and_wait (load yerine SPA’lar için domcontentloaded önerilir)
    browser_navigate_wait_until: Literal["load", "domcontentloaded", "networkidle", "commit"] = Field(
        default="domcontentloaded"
    )
    # bubus event_timeout (saniye) — os.environ TIMEOUT_* ile aynı; ilk import öncesi apply_browser_use_event_timeouts doldurur
    browser_timeout_screenshot_event: float = Field(default=25.0, ge=5.0, le=300.0)
    browser_timeout_browser_state_request: float = Field(default=45.0, ge=10.0, le=600.0)
    browser_timeout_navigate_url_event: float = Field(default=45.0, ge=15.0, le=600.0)
    # False: OOPIF/reklam iframe'lerinde DOM/CDP yarışı azalabilir; bazı sitelerde içerik eksik kalabilir
    browser_cross_origin_iframes: bool = Field(default=True)
    browser_minimum_wait_page_load_time: float = Field(default=0.28, ge=0.0, le=5.0)
    browser_wait_for_network_idle_page_load_time: float = Field(default=0.55, ge=0.0, le=10.0)
    browser_wait_between_actions: float = Field(default=0.15, ge=0.0, le=5.0)

    log_redact_telegram_token: bool = Field(default=True)

    # Aynı sınıf kimlik hatası (ör. kullanıcı adı/şifre yanlış) bu kadar kez üst üste görülünce HITL.
    auth_failure_escalation_threshold: int = Field(default=2, ge=1, le=20)

    # browser-use loop_detector: bu eşikleri aşınca HITL (stuck_subgoal) — kütüphane nudge’ı tek başına durdurmaz
    browser_stuck_stagnation_threshold: int = Field(default=8, ge=3, le=50)
    browser_stuck_repetition_threshold: int = Field(default=10, ge=3, le=50)


@lru_cache
def get_settings() -> Settings:
    return Settings()
