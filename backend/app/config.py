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
    # (network / 5xx) failures, plus a short in-process response memo.
    noaa_max_retries: int = 3
    noaa_backoff_base: float = 0.5
    noaa_cache_ttl_seconds: float = 60.0
    log_level: str = "INFO"
    # Message broker for the telemetry event path (see ADR 0007). Empty disables
    # publishing entirely, so the API and its tests run without a broker present.
    broker_url: str = ""
    broker_exchange: str = "tideline.readings"
    # How long a publish may block before we give up and carry on serving reads.
    broker_publish_timeout_seconds: float = 2.0
    # How far an observation may sit from its astronomical prediction before the
    # detector calls it surge, in metres. Mirrors SURGE_THRESHOLD in the frontend.
    surge_threshold_m: float = 0.15
    # Where messages go when the detector judges them permanently unprocessable,
    # so one bad payload cannot block the readings behind it.
    broker_dead_letter_exchange: str = "tideline.readings.dlx"

    model_config = {"env_prefix": "TIDELINE_"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
