from dataclasses import dataclass
from oslo_config import cfg
from rca_copilot.config import register_opts


@dataclass(frozen=True)
class EnrichmentConfig:
    mongo_uri: str = "mongodb://rca_admin:change-me@127.0.0.1:27017/rca_copilot?authSource=admin"
    mongo_database: str = "rca_copilot"
    parsed_logs_collection: str = "parsed_logs"
    event_edges_collection: str = "event_edges"
    incidents_collection: str = "incidents"
    worker_state_collection: str = "worker_state"
    worker_state_key: str = "enrichment_worker_v1"
    enrichment_version: str = "enrichment-v1"
    batch_size: int = 100
    poll_interval_seconds: float = 2.0
    health_file: str = "/var/lib/rca-copilot/enrichment-worker.health"

    @classmethod
    def from_conf(cls, conf: cfg.ConfigOpts = cfg.CONF) -> "EnrichmentConfig":
        register_opts(conf)
        d, w = conf.database, conf.enrichment
        return cls(
            d.connection,
            d.name,
            d.parsed_logs_collection,
            d.event_edges_collection,
            d.incidents_collection,
            d.worker_state_collection,
            w.worker_state_key,
            w.version,
            w.batch_size,
            w.poll_interval_seconds,
            w.health_file,
        )
