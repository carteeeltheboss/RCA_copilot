from __future__ import annotations

import asyncio
import signal
import sys
import time
from datetime import timedelta
from pathlib import Path

from motor.motor_asyncio import AsyncIOMotorClient

from correlation_worker.config import CorrelationConfig
from correlation_worker.repository import CorrelationRepository
from rca_copilot.service import prepare_service


class CorrelationWorker:
    def __init__(self, config: CorrelationConfig) -> None:
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
        repository = CorrelationRepository(
            parsed_collection=database[self.config.parsed_logs_collection],
            edge_collection=database[self.config.event_edges_collection],
            state_collection=database[self.config.worker_state_collection],
            worker_state_key=self.config.worker_state_key,
            correlation_version=self.config.correlation_version,
            request_id_max_gap=timedelta(seconds=self.config.request_id_max_gap_seconds),
            resource_id_max_gap=timedelta(seconds=self.config.resource_id_max_gap_seconds),
            max_events_per_group=self.config.max_events_per_group,
            skip_periodic_groups=self.config.skip_periodic_groups,
        )

        await repository.ensure_indexes()
        await self._client.admin.command("ping")
        self._mark_healthy()
        await repository.heartbeat()

        try:
            while not self._stopping:
                metrics = await repository.process_batch(self.config.batch_size)
                self._mark_healthy()
                await repository.heartbeat(metrics)
                await asyncio.sleep(self.config.poll_interval_seconds)
        finally:
            self._client.close()
            self._client = None

        return 0


async def async_main() -> int:
    worker = CorrelationWorker(CorrelationConfig.from_conf(prepare_service()))
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(signum, worker.stop)
    return await worker.run()


def main() -> int:
    return asyncio.run(async_main())


if __name__ == "__main__":
    sys.exit(main())
