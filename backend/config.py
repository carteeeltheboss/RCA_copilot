from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from oslo_config import cfg

from rca_copilot.config import register_opts


@dataclass(frozen=True)
class Settings:
    mongo_uri: str
    mongo_database: str
    mongo_raw_logs_collection: str
    mongo_parsed_logs_collection: str
    mongo_event_edges_collection: str
    mongo_incidents_collection: str
    mongo_worker_state_collection: str
    mongo_provider_configs_collection: str
    mongo_config_audit_log_collection: str
    rca_internal_service_token: str | None
    rca_provider_master_key: str | None
    rca_provider_allowed_cidrs: str
    rca_provider_allowed_hosts: str
    rca_provider_allow_localhost: bool
    rca_provider_request_timeout_seconds: int

    @classmethod
    def from_conf(cls, conf: cfg.ConfigOpts = cfg.CONF) -> "Settings":
        register_opts(conf)
        return cls(
            mongo_uri=conf.database.connection,
            mongo_database=conf.database.name,
            mongo_raw_logs_collection=conf.database.raw_logs_collection,
            mongo_parsed_logs_collection=conf.database.parsed_logs_collection,
            mongo_event_edges_collection=conf.database.event_edges_collection,
            mongo_incidents_collection=conf.database.incidents_collection,
            mongo_worker_state_collection=conf.database.worker_state_collection,
            mongo_provider_configs_collection=conf.database.provider_configs_collection,
            mongo_config_audit_log_collection=conf.database.config_audit_log_collection,
            rca_internal_service_token=conf.api.internal_service_token,
            rca_provider_master_key=conf.provider.master_key,
            rca_provider_allowed_cidrs=",".join(conf.provider.allowed_cidrs),
            rca_provider_allowed_hosts=",".join(conf.provider.allowed_hosts),
            rca_provider_allow_localhost=conf.provider.allow_localhost,
            rca_provider_request_timeout_seconds=conf.provider.request_timeout_seconds,
        )


@lru_cache
def get_settings() -> Settings:
    return Settings.from_conf()
