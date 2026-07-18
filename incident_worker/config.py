from dataclasses import dataclass
from oslo_config import cfg
from rca_copilot.config import register_opts


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
    health_file: str = "/var/lib/rca-copilot/incident-worker.health"
    correlation_worker_state_key: str = "correlation_worker_v1"

    @classmethod
    def from_conf(cls, conf: cfg.ConfigOpts = cfg.CONF) -> "IncidentConfig":
        register_opts(conf)
        d, w = conf.database, conf.incident
        return cls(
            d.connection,
            d.name,
            d.parsed_logs_collection,
            d.event_edges_collection,
            d.incidents_collection,
            d.worker_state_collection,
            w.worker_state_key,
            w.correlation_version,
            w.version,
            w.batch_size,
            w.poll_interval_seconds,
            w.max_depth,
            w.max_events,
            w.window_before_seconds,
            w.window_after_seconds,
            w.health_file,
            w.correlation_worker_state_key,
        )
