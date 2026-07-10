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
    cors_origins: str = "http://localhost:5173"
    static_dir: str = ""

    model_config = {"env_prefix": "TIDELINE_"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
