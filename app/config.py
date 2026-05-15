"""
Application configuration using pydantic-settings.
Loads values from environment variables so we can change
behaviour across envs without touching code.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central config — all values have sensible defaults."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

    # MongoDB
    mongo_uri: str = "mongodb://mongodb:27017"
    mongo_db: str = "metadata_inventory"

    # HTTP client
    request_timeout: int = 15
    max_connections: int = 20

    # App
    app_env: str = "development"
    log_level: str = "info"


settings = Settings()
