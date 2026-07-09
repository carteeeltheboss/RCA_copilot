from __future__ import annotations

import asyncio
import logging
import signal
import sys
import time
from pathlib import Path

from motor.motor_asyncio import AsyncIOMotorClient

from enrichment_worker.config import EnrichmentConfig
from enrichment_worker.repository import EnrichmentRepository


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


class EnrichmentWorker:
    def __init__(self, config: EnrichmentConfig) -> None:
        self.config = config
        self._stopping = False
        self._client: AsyncIOMotorClient | None = None

    def stop(self) -> None:
        self._stopping = True

    def _mark_healthy(self) -> None:
        Path(self.config.health_file).write_text(str(time.time()), encoding="utf-8")

    async def run(self) -> int:
        self._client = AsyncIOMotorClient(self.config.mongo_uri)
        database = self._client[self.config.mongo_database]
        repository = EnrichmentRepository(
            parsed_collection=database[self.config.parsed_logs_collection],
            edge_collection=database[self.config.event_edges_collection],
            incident_collection=database[self.config.incidents_collection],
            state_collection=database[self.config.worker_state_collection],
            worker_state_key=self.config.worker_state_key,
            enrichment_version=self.config.enrichment_version,
        )

        await repository.ensure_indexes()
        await self._client.admin.command("ping")
        self._mark_healthy()
        await repository.heartbeat()

        try:
            while not self._stopping:
                batches = await repository.process_available_batches(self.config.batch_size)
                self._mark_healthy()
                await repository.heartbeat(batches[-1] if batches else None)
                await asyncio.sleep(self.config.poll_interval_seconds)
        finally:
            self._client.close()
            self._client = None

        return 0


async def async_main() -> int:
    worker = EnrichmentWorker(EnrichmentConfig.from_env())
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(signum, worker.stop)
    return await worker.run()


def main() -> int:
    return asyncio.run(async_main())


if __name__ == "__main__":
    sys.exit(main())
