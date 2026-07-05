from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    mongo_uri: str = "mongodb://rca_admin:change-me@127.0.0.1:27017/rca_copilot?authSource=admin"
    mongo_database: str = "rca_copilot"
    mongo_raw_logs_collection: str = "raw_logs"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
