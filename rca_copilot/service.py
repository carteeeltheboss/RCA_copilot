"""Shared process initialization."""

from __future__ import annotations

from oslo_config import cfg
from oslo_log import log

from rca_copilot import config


def prepare_service(args: list[str] | None = None) -> cfg.ConfigOpts:
    conf = cfg.CONF
    log.register_options(conf)
    conf = config.init(args=args, conf=conf)
    log.setup(conf, config.PROJECT)
    return conf
