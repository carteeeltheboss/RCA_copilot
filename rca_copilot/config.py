"""Central oslo.config option registry for every RCA Copilot process."""

from __future__ import annotations

from oslo_config import cfg

PROJECT = "rca-copilot"
DEFAULT_CONFIG_FILES = ["/etc/rca-copilot/rca-copilot.conf"]

database_opts = [
    cfg.StrOpt(
        "connection",
        default="mongodb://rca_admin:change-me@127.0.0.1:27017/rca_copilot?authSource=admin",
        secret=True,
    ),
    cfg.StrOpt("name", default="rca_copilot"),
    cfg.StrOpt("raw_logs_collection", default="raw_logs"),
    cfg.StrOpt("parsed_logs_collection", default="parsed_logs"),
    cfg.StrOpt("event_edges_collection", default="event_edges"),
    cfg.StrOpt("incidents_collection", default="incidents"),
    cfg.StrOpt("worker_state_collection", default="worker_state"),
    cfg.StrOpt("provider_configs_collection", default="provider_configs"),
    cfg.StrOpt("config_audit_log_collection", default="config_audit_log"),
    cfg.IntOpt("raw_logs_retention_days", default=30, min=1),
    cfg.IntOpt("parsed_logs_retention_days", default=30, min=1),
    cfg.IntOpt("event_edges_retention_days", default=30, min=1),
]
api_opts = [
    cfg.HostAddressOpt("bind_host", default="127.0.0.1"),
    cfg.PortOpt("bind_port", default=8000),
    cfg.IntOpt("workers", default=1, min=1),
    cfg.StrOpt("internal_service_token", secret=True),
    cfg.IntOpt("max_batch_records", default=500, min=1),
    cfg.IntOpt("max_request_body_bytes", default=2097152, min=1024),
    cfg.IntOpt("batch_rate_limit_per_minute", default=120, min=1),
    cfg.StrOpt("policy_file", default="/etc/rca-copilot/policy.yaml"),
]
collector_opts = [
    cfg.URIOpt("backend_batch_url", default="http://127.0.0.1:8000/logs/batch"),
    cfg.StrOpt("state_file", default="/var/lib/rca-copilot/collector.cursor"),
    cfg.IntOpt("batch_size", default=50, min=1),
    cfg.FloatOpt("flush_interval_seconds", default=2.0, min=0.1),
    cfg.FloatOpt("request_timeout_seconds", default=5.0, min=0.1),
    cfg.IntOpt("retry_max_attempts", default=5, min=1),
    cfg.FloatOpt("retry_initial_delay_seconds", default=0.5, min=0.0),
    cfg.FloatOpt("retry_max_delay_seconds", default=8.0, min=0.0),
    cfg.StrOpt("journalctl_path", default="journalctl"),
    cfg.ListOpt(
        "units",
        default=[
            "devstack@keystone.service",
            "devstack@n-api.service",
            "devstack@n-sch.service",
            "devstack@n-cond-cell1.service",
            "devstack@n-cpu.service",
            "devstack@neutron-api.service",
            "devstack@placement-api.service",
        ],
    ),
]
parser_opts = [
    cfg.StrOpt("worker_state_key", default="parser_worker_v1"),
    cfg.StrOpt("version", default="parser-v1"),
    cfg.IntOpt("batch_size", default=100, min=1),
    cfg.FloatOpt("poll_interval_seconds", default=2.0, min=0.1),
    cfg.StrOpt("health_file", default="/var/lib/rca-copilot/parser-worker.health"),
]
correlation_opts = [
    cfg.StrOpt("worker_state_key", default="correlation_worker_v1"),
    cfg.StrOpt("version", default="correlation-v1"),
    cfg.IntOpt("batch_size", default=100, min=1),
    cfg.FloatOpt("poll_interval_seconds", default=2.0, min=0.1),
    cfg.IntOpt("request_id_max_gap_seconds", default=300, min=0),
    cfg.IntOpt("resource_id_max_gap_seconds", default=600, min=0),
    cfg.IntOpt("max_events_per_group", default=100, min=1),
    cfg.BoolOpt("skip_periodic_groups", default=True),
    cfg.StrOpt("health_file", default="/var/lib/rca-copilot/correlation-worker.health"),
]
incident_opts = [
    cfg.StrOpt("worker_state_key", default="incident_worker_v1"),
    cfg.StrOpt("correlation_worker_state_key", default="correlation_worker_v1"),
    cfg.StrOpt("correlation_version", default="correlation-v1"),
    cfg.StrOpt("version", default="incident-v1"),
    cfg.IntOpt("batch_size", default=100, min=1),
    cfg.FloatOpt("poll_interval_seconds", default=2.0, min=0.1),
    cfg.IntOpt("max_depth", default=3, min=1),
    cfg.IntOpt("max_events", default=100, min=1),
    cfg.IntOpt("window_before_seconds", default=600, min=0),
    cfg.IntOpt("window_after_seconds", default=120, min=0),
    cfg.StrOpt("health_file", default="/var/lib/rca-copilot/incident-worker.health"),
]
enrichment_opts = [
    cfg.StrOpt("worker_state_key", default="enrichment_worker_v1"),
    cfg.StrOpt("version", default="enrichment-v1"),
    cfg.IntOpt("batch_size", default=100, min=1),
    cfg.FloatOpt("poll_interval_seconds", default=2.0, min=0.1),
    cfg.StrOpt("health_file", default="/var/lib/rca-copilot/enrichment-worker.health"),
]
provider_opts = [
    cfg.StrOpt("master_key", secret=True),
    cfg.ListOpt("allowed_cidrs", default=[]),
    cfg.ListOpt("allowed_hosts", default=[]),
    cfg.BoolOpt("allow_localhost", default=False),
    cfg.IntOpt("request_timeout_seconds", default=10, min=1),
]

GROUPS = {
    "database": database_opts,
    "api": api_opts,
    "collector": collector_opts,
    "parser": parser_opts,
    "correlation": correlation_opts,
    "incident": incident_opts,
    "enrichment": enrichment_opts,
    "provider": provider_opts,
}


def register_opts(conf: cfg.ConfigOpts = cfg.CONF) -> None:
    for group, opts in GROUPS.items():
        conf.register_opts(opts, group=group)


def init(args: list[str] | None = None, conf: cfg.ConfigOpts = cfg.CONF) -> cfg.ConfigOpts:
    register_opts(conf)
    conf(args=args, project=PROJECT, default_config_files=DEFAULT_CONFIG_FILES)
    return conf


def list_opts() -> list[tuple[str, list[cfg.Opt]]]:
    return list(GROUPS.items())
