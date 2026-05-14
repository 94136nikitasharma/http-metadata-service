"""
Application configuration using pydantic-settings.

All configurable values are loaded from environment variables,
making it easy to adjust behaviour across different environments
(development, testing, production) without code changes.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration for the HTTP Metadata Inventory Service."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

    # MongoDB
    mongo_uri: str = "mongodb://mongodb:27017"
    mongo_db: str = "metadata_inventory"

    # HTTP client behaviour
    request_timeout: int = 15  # seconds
    max_connections: int = 20  # connection pool limit

    # Application
    app_env: str = "development"
    log_level: str = "info"


# Singleton instance – imported throughout the application
settings = Settings()
