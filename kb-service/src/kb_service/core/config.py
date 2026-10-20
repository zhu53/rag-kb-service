from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """全局配置：一律从环境变量 / .env 读取，代码里禁止硬编码。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App
    app_name: str = "kb-service"
    env: Literal["dev", "test", "prod"] = "dev"
    debug: bool = False
    log_level: str = "INFO"

    # Security
    secret_key: str = Field(min_length=16)
    access_token_expire_minutes: int = 60
    algorithm: str = "HS256"

    # Database / Cache（W7、W10 启用）
    database_url: str = "postgresql+asyncpg://kb:kb@localhost:5432/kb"
    redis_url: str = "redis://localhost:6379/0"

    # LLM（W12 启用）
    llm_api_key: str | None = None
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"
    embedding_model: str = "text-embedding-3-small"
    embedding_dim: int = 1536


@lru_cache
def get_settings() -> Settings:
    """缓存配置实例；测试里用 get_settings.cache_clear() 重置。"""
    return Settings()  # type: ignore[call-arg]
