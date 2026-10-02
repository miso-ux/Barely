from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration read from environment variables (see .env.example).

    Business rules (limits, prices, penalties) are NOT here; they live in the `Setting` table.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://barely:barely@db:5432/barely"
    secret_key: str = "change-me-demo-secret"
    app_env: str = "development"
    # Due dates are calendar dates in this zone; all timestamps are stored in UTC.
    timezone: str = "Europe/Bratislava"


@lru_cache
def get_settings() -> Settings:
    return Settings()
