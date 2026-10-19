from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

API_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=API_ROOT / ".env", extra="ignore")

    app_env: Literal["development", "test", "production"] = "development"
    session_secret: SecretStr = SecretStr("change-me")
    cors_origins: str = "http://localhost:3000"
    log_level: str = "info"

    database_url: str = "postgresql://localhost:5432/tasteroute"
    db_statement_cache_size: int = 100  # set 0 for the Supavisor transaction pooler

    qloo_api_key: SecretStr = SecretStr("")
    qloo_base_url: str = "https://hackathon.api.qloo.com"
    qloo_rps: float = 4.0
    qloo_max_calls_per_run: int = 120
    qloo_monthly_limit: int = 10_000
    qloo_cache_ttl_hours: int = 72
    qloo_timeout_seconds: float = 20.0

    llm_provider: Literal["ollama_cloud", "fake"] = "ollama_cloud"
    ollama_base_url: str = "https://ollama.com"
    ollama_api_key: SecretStr = SecretStr("")
    ollama_model: str = "gemma4:31b"
    llm_timeout_seconds: float = 90.0
    llm_temperature_tools: float = 0.2
    llm_temperature_writing: float = 0.7
    llm_max_steps_per_phase: int = 12
    llm_max_calls_per_run: int = 80

    hunter_api_key: SecretStr = SecretStr("")
    hunter_max_calls_per_run: int = 25
    osm_user_agent: str = "TasteRoute/0.1 (contact: you@example.com)"
    nominatim_base_url: str = "https://nominatim.openstreetmap.org"
    overpass_base_url: str = "https://overpass-api.de/api/interpreter"
    website_fetch_timeout_seconds: float = 12.0

    demo_mode_enabled: bool = True
    demo_run_id: str = ""
    public_runs_per_ip_per_day: int = 3
    max_venues_per_run: int = 60
    max_outreach_venues_per_run: int = 25
    pack_fashion_enabled: bool = False

    opt_out_line: str = Field(
        default="If you'd rather not hear from me, reply 'no thanks' and I won't contact you again."
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
