from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="KBCLI_", env_file=".env", extra="ignore"
    )
    data_file: Path = Path("kbs.json")
    log_level: str = "INFO"


@lru_cache  # D3 学过的单例阀门——这里可以用 functools 的了
def get_settings() -> Settings:
    return Settings()
