"""Application configuration (environment variables / .env)."""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+psycopg://app:app@localhost:5432/naklady"
    secret_key: str = "change-me-in-production"
    token_hours: int = 24 * 14
    cookie_secure: bool = False

    # Where uploaded / synced source files are stored
    storage_dir: Path = Path("./data/files")

    # Public base URL of the app (used for OAuth redirect)
    app_base_url: str = "http://localhost:8000"

    # Bootstrap admin (created on startup if no user exists)
    admin_email: str | None = None
    admin_password: str | None = None
    admin_name: str = "Administrátor"

    # Claude API (document extraction)
    anthropic_api_key: str | None = None
    claude_model: str = "claude-opus-5-5"

    # Google OAuth (Drive + Gmail) – OAuth client of type "Web application"
    google_client_id: str | None = None
    google_client_secret: str | None = None

    # eKasa (Finančná správa) – public receipt lookup endpoint
    ekasa_url: str = "https://ekasa.financnasprava.sk/mdu/api/v1/opd/receipt/find"
    ekasa_enabled: bool = True

    timezone: str = "Europe/Bratislava"
    run_scheduler: bool = False


@lru_cache
def get_config() -> Config:
    return Config()
