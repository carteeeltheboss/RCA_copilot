from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class BatchClient:
    url: str
    timeout_seconds: float
    max_attempts: int
    initial_delay_seconds: float
    max_delay_seconds: float
    sleep: Callable[[float], None] = time.sleep

    def post_batch(self, records: list[dict[str, Any]]) -> bool:
        if not records:
            return True

        delay = self.initial_delay_seconds
        payload = {"records": records}
        for attempt in range(1, self.max_attempts + 1):
            try:
                response = httpx.post(self.url, json=payload, timeout=self.timeout_seconds)
                if 200 <= response.status_code < 300:
                    return True
            except httpx.HTTPError:
                pass

            if attempt < self.max_attempts:
                self.sleep(delay)
                delay = min(delay * 2, self.max_delay_seconds)

        return False
