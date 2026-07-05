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


@dataclass(frozen=True)
class IncidentConfig:
    mongo_uri: str = "mongodb://rca_admin:change-me@127.0.0.1:27017/rca_copilot?authSource=admin"
    mongo_database: str = "rca_copilot"
    parsed_logs_collection: str = "parsed_logs"
    event_edges_collection: str = "event_edges"
    incidents_collection: str = "incidents"
    worker_state_collection: str = "worker_state"
    worker_state_key: str = "incident_worker_v1"
    correlation_version: str = "correlation-v1"
    incident_version: str = "incident-v1"
    batch_size: int = 100
    poll_interval_seconds: float = 2.0
    max_depth: int = 3
    max_events: int = 100
    window_before_seconds: int = 600
    window_after_seconds: int = 120
    health_file: str = "/tmp/rca-copilot-incident-worker.health"

    @classmethod
    def from_env(cls) -> IncidentConfig:
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
            incidents_collection=os.getenv(
                "MONGO_INCIDENTS_COLLECTION",
                cls.incidents_collection,
            ),
            worker_state_collection=os.getenv(
                "MONGO_WORKER_STATE_COLLECTION",
                cls.worker_state_collection,
            ),
            worker_state_key=os.getenv("INCIDENT_WORKER_STATE_KEY", cls.worker_state_key),
            correlation_version=os.getenv("CORRELATION_VERSION", cls.correlation_version),
            incident_version=os.getenv("INCIDENT_VERSION", cls.incident_version),
            batch_size=_env_int("INCIDENT_BATCH_SIZE", cls.batch_size),
            poll_interval_seconds=_env_float(
                "INCIDENT_POLL_INTERVAL_SECONDS",
                cls.poll_interval_seconds,
            ),
            max_depth=_env_int("INCIDENT_MAX_DEPTH", cls.max_depth),
            max_events=_env_int("INCIDENT_MAX_EVENTS", cls.max_events),
            window_before_seconds=_env_int(
                "INCIDENT_WINDOW_BEFORE_SECONDS",
                cls.window_before_seconds,
            ),
            window_after_seconds=_env_int(
                "INCIDENT_WINDOW_AFTER_SECONDS",
                cls.window_after_seconds,
            ),
            health_file=os.getenv("INCIDENT_HEALTH_FILE", cls.health_file),
        )
