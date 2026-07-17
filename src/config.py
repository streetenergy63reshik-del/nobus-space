"""Base configuration for the orchestrator development sandbox."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from .env if present."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Nobus Orchestrator Dev"
    debug: bool = True

    # Defaults for local sandbox; override via .env when needed.
    default_agent_timeout: int = 30

    # LLM integration is disabled by default in the sandbox.
    llm_enabled: bool = False
    openai_api_key: str = ""


settings = Settings()
