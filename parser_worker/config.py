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
class ParserConfig:
    mongo_uri: str = "mongodb://rca_admin:change-me@127.0.0.1:27017/rca_copilot?authSource=admin"
    mongo_database: str = "rca_copilot"
    raw_logs_collection: str = "raw_logs"
    parsed_logs_collection: str = "parsed_logs"
    parser_version: str = "parser-v1"
    batch_size: int = 100
    poll_interval_seconds: float = 2.0
    health_file: str = "/tmp/rca-copilot-parser-worker.health"

    @classmethod
    def from_env(cls) -> ParserConfig:
        return cls(
            mongo_uri=os.getenv("MONGO_URI", cls.mongo_uri),
            mongo_database=os.getenv("MONGO_DATABASE", cls.mongo_database),
            raw_logs_collection=os.getenv("MONGO_RAW_LOGS_COLLECTION", cls.raw_logs_collection),
            parsed_logs_collection=os.getenv(
                "MONGO_PARSED_LOGS_COLLECTION",
                cls.parsed_logs_collection,
            ),
            parser_version=os.getenv("PARSER_VERSION", cls.parser_version),
            batch_size=_env_int("PARSER_BATCH_SIZE", cls.batch_size),
            poll_interval_seconds=_env_float(
                "PARSER_POLL_INTERVAL_SECONDS",
                cls.poll_interval_seconds,
            ),
            health_file=os.getenv("PARSER_HEALTH_FILE", cls.health_file),
        )

