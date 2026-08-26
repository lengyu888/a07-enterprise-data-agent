from functools import lru_cache
from threading import RLock
from typing import ClassVar, Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


_runtime_secret_lock = RLock()
_runtime_deepseek_api_key: str | None = None
_runtime_deepseek_model = "deepseek-v4-pro"
SUPPORTED_DEEPSEEK_MODELS = ("deepseek-v4-pro", "deepseek-v4-flash")


def get_runtime_deepseek_api_key() -> str | None:
    with _runtime_secret_lock:
        return _runtime_deepseek_api_key


def get_runtime_deepseek_model() -> str:
    with _runtime_secret_lock:
        return _runtime_deepseek_model


def replace_runtime_deepseek_config(value: str | None, model: str) -> tuple[str | None, str]:
    """Atomically replace process-local credentials and return the previous state."""
    if model not in SUPPORTED_DEEPSEEK_MODELS:
        raise ValueError("Unsupported DeepSeek model")
    normalized = value.strip() if value and value.strip() else None
    global _runtime_deepseek_api_key, _runtime_deepseek_model
    with _runtime_secret_lock:
        previous = (_runtime_deepseek_api_key, _runtime_deepseek_model)
        _runtime_deepseek_api_key = normalized
        _runtime_deepseek_model = model
        return previous


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "A07 企业数据底座智能问析 Agent"
    app_env: str = "local"
    app_version: str = "0.7.0"
    database_url: str = "postgresql+psycopg://a07_app:a07_local_dev_change_me@postgres:5432/a07_agent"

    deepseek_base_url: ClassVar[str] = "https://api.deepseek.com"
    deepseek_reasoning_effort: ClassVar[Literal["high", "max"]] = "high"
    embedding_model: str = "BAAI/bge-small-zh-v1.5"
    embedding_cache_path: str = "/opt/fastembed-cache"

    @property
    def deepseek_configured(self) -> bool:
        return bool(self.resolved_deepseek_api_key)

    @property
    def deepseek_config_source(self) -> str:
        return "runtime" if get_runtime_deepseek_api_key() else "none"

    @property
    def deepseek_model(self) -> str:
        return get_runtime_deepseek_model()

    @property
    def resolved_deepseek_api_key(self) -> str | None:
        return get_runtime_deepseek_api_key()


@lru_cache
def get_settings() -> Settings:
    return Settings()
