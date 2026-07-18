from __future__ import annotations

import uvicorn

from rca_copilot.service import prepare_service


def main() -> None:
    conf = prepare_service()
    uvicorn.run(
        "backend.main:app",
        host=conf.api.bind_host,
        port=conf.api.bind_port,
        workers=conf.api.workers,
    )
