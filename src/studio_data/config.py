"""Application settings loaded from environment variables.

Uses pydantic-settings to validate and parse env vars (or a .env file)
into typed Python objects. This gives us a single source of truth for
configuration with automatic validation on startup — if DATABASE_URL
is missing, the app fails fast with a clear error instead of crashing
later with a cryptic psycopg connection error.
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings

# Resolve the .env file relative to the project root (studio-data/).
# Path: config.py → studio_data/ → src/ → studio-data/
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    """Configuration for the studio-data service.

    All values can be overridden via environment variables or a .env file.
    DATABASE_URL is required; everything else has sensible defaults.
    """

    database_url: str = "postgresql://studio:changeme@localhost:5432/studioos"

    model_config = {
        "env_file": str(PROJECT_ROOT / ".env"),
        "env_file_encoding": "utf-8",
    }


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (parsed once, reused everywhere)."""
    return Settings()
