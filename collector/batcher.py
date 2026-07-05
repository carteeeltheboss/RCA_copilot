from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class LogBatcher:
    batch_size: int
    flush_interval_seconds: float
    clock: Callable[[], float] = time.monotonic
    records: list[dict[str, Any]] = field(default_factory=list)
    last_flush_at: float = field(init=False)

    def __post_init__(self) -> None:
        self.last_flush_at = self.clock()

    def add(self, record: dict[str, Any]) -> list[dict[str, Any]] | None:
        self.records.append(record)
        if len(self.records) >= self.batch_size:
            return self.flush()
        return None

    def due(self) -> bool:
        return bool(self.records) and self.clock() - self.last_flush_at >= self.flush_interval_seconds

    def flush(self) -> list[dict[str, Any]]:
        batch = self.records
        self.records = []
        self.last_flush_at = self.clock()
        return batch
