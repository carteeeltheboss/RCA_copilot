from __future__ import annotations

from oslo_config import cfg

from rca_copilot.config import DEFAULT_CONFIG_FILES, register_opts


def load_config(config_file: str | None = None) -> cfg.ConfigOpts:
    conf = cfg.ConfigOpts()
    register_opts(conf)
    files = [config_file] if config_file else DEFAULT_CONFIG_FILES
    conf(args=[], project="rca-copilot", default_config_files=files)
    return conf


def backend_url(conf: cfg.ConfigOpts) -> str:
    return f"http://{conf.api.bind_host}:{conf.api.bind_port}"
