from __future__ import annotations

from dataclasses import dataclass, field

from oslo_config import cfg

from rca_copilot.config import register_opts

DEFAULT_UNITS = (
    "devstack@keystone.service",
    "devstack@n-api.service",
    "devstack@n-sch.service",
    "devstack@n-cond-cell1.service",
    "devstack@n-cpu.service",
    "devstack@neutron-api.service",
    "devstack@placement-api.service",
)


@dataclass(frozen=True)
class CollectorConfig:
    backend_batch_url: str = "http://127.0.0.1:8000/logs/batch"
    state_file: str = "/var/lib/rca-copilot/collector.cursor"
    batch_size: int = 50
    flush_interval_seconds: float = 2.0
    request_timeout_seconds: float = 5.0
    retry_max_attempts: int = 5
    retry_initial_delay_seconds: float = 0.5
    retry_max_delay_seconds: float = 8.0
    journalctl_path: str = "journalctl"
    units: tuple[str, ...] = field(default_factory=lambda: DEFAULT_UNITS)
    internal_service_token: str | None = None

    @classmethod
    def from_conf(cls, conf: cfg.ConfigOpts = cfg.CONF) -> "CollectorConfig":
        register_opts(conf)
        group = conf.collector
        return cls(
            backend_batch_url=group.backend_batch_url,
            state_file=group.state_file,
            batch_size=group.batch_size,
            flush_interval_seconds=group.flush_interval_seconds,
            request_timeout_seconds=group.request_timeout_seconds,
            retry_max_attempts=group.retry_max_attempts,
            retry_initial_delay_seconds=group.retry_initial_delay_seconds,
            retry_max_delay_seconds=group.retry_max_delay_seconds,
            journalctl_path=group.journalctl_path,
            units=tuple(group.units),
            internal_service_token=conf.api.internal_service_token,
        )
