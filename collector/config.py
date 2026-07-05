from __future__ import annotations

import os
from dataclasses import dataclass, field


DEFAULT_UNITS = (
    "devstack@keystone.service",
    "devstack@n-api.service",
    "devstack@n-sch.service",
    "devstack@n-cond-cell1.service",
    "devstack@n-cpu.service",
    "devstack@neutron-api.service",
    "devstack@placement-api.service",
)


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


def _env_units(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return tuple(unit.strip() for unit in value.split(",") if unit.strip())


@dataclass(frozen=True)
class CollectorConfig:
    backend_batch_url: str = "http://127.0.0.1:8000/logs/batch"
    state_file: str = "/var/lib/rca-copilot-journald-collector/journal.cursor"
    batch_size: int = 50
    flush_interval_seconds: float = 2.0
    request_timeout_seconds: float = 5.0
    retry_max_attempts: int = 5
    retry_initial_delay_seconds: float = 0.5
    retry_max_delay_seconds: float = 8.0
    journalctl_path: str = "journalctl"
    units: tuple[str, ...] = field(default_factory=lambda: DEFAULT_UNITS)

    @classmethod
    def from_env(cls) -> CollectorConfig:
        return cls(
            backend_batch_url=os.getenv("RCA_COLLECTOR_BACKEND_URL", cls.backend_batch_url),
            state_file=os.getenv("RCA_COLLECTOR_STATE_FILE", cls.state_file),
            batch_size=_env_int("RCA_COLLECTOR_BATCH_SIZE", cls.batch_size),
            flush_interval_seconds=_env_float(
                "RCA_COLLECTOR_FLUSH_INTERVAL_SECONDS",
                cls.flush_interval_seconds,
            ),
            request_timeout_seconds=_env_float(
                "RCA_COLLECTOR_REQUEST_TIMEOUT_SECONDS",
                cls.request_timeout_seconds,
            ),
            retry_max_attempts=_env_int(
                "RCA_COLLECTOR_RETRY_MAX_ATTEMPTS",
                cls.retry_max_attempts,
            ),
            retry_initial_delay_seconds=_env_float(
                "RCA_COLLECTOR_RETRY_INITIAL_DELAY_SECONDS",
                cls.retry_initial_delay_seconds,
            ),
            retry_max_delay_seconds=_env_float(
                "RCA_COLLECTOR_RETRY_MAX_DELAY_SECONDS",
                cls.retry_max_delay_seconds,
            ),
            journalctl_path=os.getenv("RCA_COLLECTOR_JOURNALCTL_PATH", cls.journalctl_path),
            units=_env_units("RCA_COLLECTOR_UNITS", DEFAULT_UNITS),
        )
