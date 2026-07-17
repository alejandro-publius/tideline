from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """App configuration, overridable via TIDELINE_* environment variables."""

    database_url: str = "sqlite:///./tideline.db"
    noaa_base_url: str = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"
    cache_ttl_minutes: int = 10
    predictions_ttl_minutes: int = 12 * 60
    # background sweep that keeps surge history accumulating without visitors
    # (0 disables it)
    history_refresh_minutes: int = 30
    # per-client API request budget: token bucket, refilled continuously
    # (0 disables limiting)
    rate_limit_per_minute: int = 120
    cors_origins: str = "http://localhost:5173"
    static_dir: str = ""
    # NOAA client resilience: retries with exponential backoff on transient
    # (network / 5xx) failures, plus a per-series cooldown after a failure so
    # an outage is served from stale cache instead of re-paying the retry cost
    # on every request (0 disables the cooldown).
    noaa_max_retries: int = 3
    noaa_backoff_base: float = 0.5
    noaa_failure_cooldown_seconds: float = 60.0
    log_level: str = "INFO"

    model_config = {"env_prefix": "TIDELINE_"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
