
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration; secrets are supplied by the deployment environment."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    app_name: str = "Personal Finance API"
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_jwt_secret: str = ""
    supabase_service_role_key: str | None = None
    max_export_rows: int = 10_000
    supported_currencies: tuple[str, ...] = ("CLP", "USD", "EUR")


async def get_settings() -> Settings:
    return Settings()
