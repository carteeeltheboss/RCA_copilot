from dataclasses import dataclass
from oslo_config import cfg
from rca_copilot.config import register_opts


@dataclass(frozen=True)
class ParserConfig:
    mongo_uri: str = "mongodb://rca_admin:change-me@127.0.0.1:27017/rca_copilot?authSource=admin"
    mongo_database: str = "rca_copilot"
    raw_logs_collection: str = "raw_logs"
    parsed_logs_collection: str = "parsed_logs"
    worker_state_collection: str = "worker_state"
    worker_state_key: str = "parser_worker_v1"
    parser_version: str = "parser-v1"
    batch_size: int = 100
    poll_interval_seconds: float = 2.0
    health_file: str = "/var/lib/rca-copilot/parser-worker.health"

    @classmethod
    def from_conf(cls, conf: cfg.ConfigOpts = cfg.CONF) -> "ParserConfig":
        register_opts(conf)
        d, w = conf.database, conf.parser
        return cls(
            d.connection,
            d.name,
            d.raw_logs_collection,
            d.parsed_logs_collection,
            d.worker_state_collection,
            w.worker_state_key,
            w.version,
            w.batch_size,
            w.poll_interval_seconds,
            w.health_file,
        )
