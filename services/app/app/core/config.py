from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "A07 企业数据底座智能问析 Agent"
    app_env: str = "local"
    app_version: str = "0.3.0"
    database_url: str = "postgresql+psycopg://a07_app:a07_local_dev_change_me@postgres:5432/a07_agent"

    deepseek_api_key: str | None = Field(default=None, repr=False)
    deepseek_api_key_file: str | None = None
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-v4-pro"
    deepseek_reasoning_effort: Literal["high", "max"] = "high"

    @property
    def deepseek_configured(self) -> bool:
        return bool(self.resolved_deepseek_api_key)

    @property
    def resolved_deepseek_api_key(self) -> str | None:
        if self.deepseek_api_key and self.deepseek_api_key.strip():
            return self.deepseek_api_key.strip()

        if self.deepseek_api_key_file:
            secret_path = Path(self.deepseek_api_key_file)
            if secret_path.is_file():
                value = secret_path.read_text(encoding="utf-8").strip()
                return value or None

        return None


@lru_cache
def get_settings() -> Settings:
    return Settings()
