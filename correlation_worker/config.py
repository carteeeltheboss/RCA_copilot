from dataclasses import dataclass
from oslo_config import cfg
from rca_copilot.config import register_opts


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
    health_file: str = "/var/lib/rca-copilot/correlation-worker.health"

    @classmethod
    def from_conf(cls, conf: cfg.ConfigOpts = cfg.CONF) -> "CorrelationConfig":
        register_opts(conf)
        d, w = conf.database, conf.correlation
        return cls(
            d.connection,
            d.name,
            d.parsed_logs_collection,
            d.event_edges_collection,
            d.worker_state_collection,
            w.worker_state_key,
            w.version,
            w.batch_size,
            w.poll_interval_seconds,
            w.request_id_max_gap_seconds,
            w.resource_id_max_gap_seconds,
            w.max_events_per_group,
            w.skip_periodic_groups,
            w.health_file,
        )
