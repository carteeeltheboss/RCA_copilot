from __future__ import annotations

import os
from dataclasses import dataclass


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return int(value)


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return float(value)


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class CorrelationConfig:
    mongo_uri: str = "mongodb://rca_admin:change-me@127.0.0.1:27017/rca_copilot?authSource=admin"
    mongo_database: str = "rca_copilot"
    parsed_logs_collection: str = "parsed_logs"
    event_edges_collection: str = "event_edges"
    worker_state_collection: str = "worker_state"
    worker_state_key: str = "correlation_worker_v1"
    correlation_version: str = "correlation-v1"
    batch_size: int = 100
    poll_interval_seconds: float = 2.0
    request_id_max_gap_seconds: int = 300
    resource_id_max_gap_seconds: int = 600
    max_events_per_group: int = 100
    skip_periodic_groups: bool = True
    health_file: str = "/tmp/rca-copilot-correlation-worker.health"

    @classmethod
    def from_env(cls) -> CorrelationConfig:
        return cls(
            mongo_uri=os.getenv("MONGO_URI", cls.mongo_uri),
            mongo_database=os.getenv("MONGO_DATABASE", cls.mongo_database),
            parsed_logs_collection=os.getenv(
                "MONGO_PARSED_LOGS_COLLECTION",
                cls.parsed_logs_collection,
            ),
            event_edges_collection=os.getenv(
                "MONGO_EVENT_EDGES_COLLECTION",
                cls.event_edges_collection,
            ),
            worker_state_collection=os.getenv(
                "MONGO_WORKER_STATE_COLLECTION",
                cls.worker_state_collection,
            ),
            worker_state_key=os.getenv("CORRELATION_WORKER_STATE_KEY", cls.worker_state_key),
            correlation_version=os.getenv("CORRELATION_VERSION", cls.correlation_version),
            batch_size=_env_int("CORRELATION_BATCH_SIZE", cls.batch_size),
            poll_interval_seconds=_env_float(
                "CORRELATION_POLL_INTERVAL_SECONDS",
                cls.poll_interval_seconds,
            ),
            request_id_max_gap_seconds=_env_int(
                "CORRELATION_REQUEST_ID_MAX_GAP_SECONDS",
                cls.request_id_max_gap_seconds,
            ),
            resource_id_max_gap_seconds=_env_int(
                "CORRELATION_RESOURCE_ID_MAX_GAP_SECONDS",
                cls.resource_id_max_gap_seconds,
            ),
            max_events_per_group=_env_int(
                "CORRELATION_MAX_EVENTS_PER_GROUP",
                cls.max_events_per_group,
            ),
            skip_periodic_groups=_env_bool(
                "CORRELATION_SKIP_PERIODIC_GROUPS",
                cls.skip_periodic_groups,
            ),
            health_file=os.getenv("CORRELATION_HEALTH_FILE", cls.health_file),
        )
