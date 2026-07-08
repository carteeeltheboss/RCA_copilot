from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    mongo_uri: str = "mongodb://rca_admin:change-me@127.0.0.1:27017/rca_copilot?authSource=admin"
    mongo_database: str = "rca_copilot"
    mongo_raw_logs_collection: str = "raw_logs"
    mongo_parsed_logs_collection: str = "parsed_logs"
    mongo_event_edges_collection: str = "event_edges"
    mongo_incidents_collection: str = "incidents"
    mongo_worker_state_collection: str = "worker_state"
    mongo_provider_configs_collection: str = "provider_configs"
    mongo_config_audit_log_collection: str = "config_audit_log"

    rca_internal_service_token: str | None = None
    rca_provider_master_key: str | None = None
    rca_provider_allowed_cidrs: str = ""
    rca_provider_allowed_hosts: str = ""
    rca_provider_allow_localhost: bool = False
    rca_provider_request_timeout_seconds: int = 10

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
